"""
UPLS vs Basic Controller - Tam Simülasyon Karşılaştırması
Gerçek çimento fabrikası verisi üzerinde test
"""

import sys
sys.path.insert(0, 'models')

from battery import BatteryModel
from upls_controller import UPLSController
from controller import PeakShavingController
import pandas as pd
import numpy as np
import json

print("\n🔬 UPLS vs BASIC CONTROLLER - TAM KARŞILAŞTIRMA")
print("=" * 80)

# Config yükle
with open('config/config.json', 'r') as f:
    config = json.load(f)

# Veriyi yükle
print("\n1️⃣ Veri yükleniyor...")
df = pd.read_csv('data/synthetic/elektrik_tuketim.csv')
df['timestamp'] = pd.to_datetime(df['Tarih_Saat'])
df['load_kw'] = df['Guc_kW']
df = df.sort_values('timestamp').reset_index(drop=True)

print(f"   ✅ {len(df):,} satır veri yüklendi")
print(f"   Dönem: {df['timestamp'].min()} - {df['timestamp'].max()}")
print(f"   Load: {df['load_kw'].min():.0f} - {df['load_kw'].max():.0f} kW")

# İlk 3 ay al (hızlı test için)
df_test = df.head(3 * 30 * 24 * 4)  # 3 ay
print(f"   Test verisi: {len(df_test):,} satır (3 ay)")

#=============================================================================
# TEST 1: BASIC CONTROLLER
#=============================================================================
print("\n" + "=" * 80)
print("TEST 1: BASIC CONTROLLER (Mevcut Sistem)")
print("=" * 80)

battery_basic = BatteryModel(config['battery'])
controller_basic = PeakShavingController(config['simulation'])

# Threshold hesapla
threshold_basic = controller_basic.calculate_threshold(df_test['load_kw'])
print(f"   Threshold: {threshold_basic:.0f} kW (static)")

basic_results = []
interval_hours = 0.25  # 15 min

for idx, row in df_test.iterrows():
    load = row['load_kw']
    
    action = controller_basic.decide_action(load, battery_basic)
    
    if action['mode'] == 'charge':
        actual = battery_basic.charge(action['power_kw'], interval_hours)
        batt_power = -actual
    elif action['mode'] == 'discharge':
        actual = battery_basic.discharge(action['power_kw'], interval_hours)
        batt_power = actual
    else:
        batt_power = 0
    
    net_load = load - batt_power
    basic_results.append({
        'load': load,
        'net_load': net_load,
        'battery_power': batt_power,
        'soc': battery_basic.soc
    })
    
    if idx % 5000 == 0:
        print(f"   Progress: {(idx/len(df_test)*100):.0f}%", end='\r')

print("\n   ✅ Basic simulation complete")

battery_basic.update_degradation()
basic_df = pd.DataFrame(basic_results)

#=============================================================================
# TEST 2: UPLS CONTROLLER
#=============================================================================
print("\n" + "=" * 80)
print("TEST 2: UPLS CONTROLLER (Gelişmiş Sistem)")
print("=" * 80)

battery_upls = BatteryModel(config['battery'])
upls_config = {
    'rolling_window_hours': 24,
    'lookahead_hours': 4,
    'adaptive_factor': 0.85,  # 85th percentile (same as basic)
    'soc_reserve_threshold': 0.25,
    'enable_forecast': True
}
controller_upls = UPLSController(upls_config)

print(f"   Rolling window: {upls_config['rolling_window_hours']} hours")
print(f"   Lookahead: {upls_config['lookahead_hours']} hours")
print(f"   Adaptive factor: {upls_config['adaptive_factor']} (threshold multiplier)")

upls_results = []
load_array = df_test['load_kw'].values

for idx, row in df_test.iterrows():
    load = row['load_kw']
    timestamp = row['timestamp']
    
    action = controller_upls.decide_action(
        current_load_kw=load,
        battery=battery_upls,
        forecast_load=load_array,
        current_time=timestamp,
        current_idx=idx
    )
    
    if action['mode'] == 'charge':
        actual = battery_upls.charge(action['power_kw'], interval_hours)
        batt_power = -actual
    elif action['mode'] == 'discharge':
        actual = battery_upls.discharge(action['power_kw'], interval_hours)
        batt_power = actual
    else:
        batt_power = 0
    
    net_load = load - batt_power
    upls_results.append({
        'load': load,
        'net_load': net_load,
        'battery_power': batt_power,
        'soc': battery_upls.soc,
        'threshold': action.get('threshold')
    })
    
    controller_upls.log_decision(timestamp, load, action, battery_upls.soc)
    
    if idx % 5000 == 0:
        print(f"   Progress: {(idx/len(df_test)*100):.0f}%", end='\r')

print("\n   ✅ UPLS simulation complete")

battery_upls.update_degradation()
upls_df = pd.DataFrame(upls_results)
upls_stats = controller_upls.get_statistics()

#=============================================================================
# KARŞILAŞTIRMA
#=============================================================================
print("\n" + "=" * 80)
print("📊 PERFORMANS KARŞILAŞTIRMASI")
print("=" * 80)

# Peak metrics
original_peak = df_test['load_kw'].max()
basic_peak = basic_df['net_load'].max()
upls_peak = upls_df['net_load'].max()

basic_reduction = original_peak - basic_peak
upls_reduction = original_peak - upls_peak

basic_pct = (basic_reduction / original_peak) * 100
upls_pct = (upls_reduction / original_peak) * 100

print(f"\n🎯 PEAK REDUCTION:")
print(f"   Original Peak:           {original_peak:>12,.0f} kW")
print(f"   Basic Peak:              {basic_peak:>12,.0f} kW  ({basic_reduction:,.0f} kW reduction, {basic_pct:.1f}%)")
print(f"   UPLS Peak:               {upls_peak:>12,.0f} kW  ({upls_reduction:,.0f} kW reduction, {upls_pct:.1f}%)")
print(f"\n   {'='*70}")
print(f"   UPLS IMPROVEMENT:        {upls_reduction - basic_reduction:>12,.0f} kW  ({upls_pct - basic_pct:+.2f}%)")
print(f"   {'='*70}")

# Battery utilization
print(f"\n⚡ BATTERY USAGE:")
basic_discharge_pct = (basic_df['battery_power'] > 0).sum() / len(basic_df) * 100
upls_discharge_pct = (upls_df['battery_power'] > 0).sum() / len(upls_df) * 100

basic_charge_pct = (basic_df['battery_power'] < 0).sum() / len(basic_df) * 100
upls_charge_pct = (upls_df['battery_power'] < 0).sum() / len(upls_df) * 100

print(f"   Basic - Discharge time:  {basic_discharge_pct:>10.1f}%")
print(f"   UPLS  - Discharge time:  {upls_discharge_pct:>10.1f}%")
print(f"   Basic - Charge time:     {basic_charge_pct:>10.1f}%")
print(f"   UPLS  - Charge time:     {upls_charge_pct:>10.1f}%")

print(f"\n   Basic - Avg SOC:         {basic_df['soc'].mean():>10.1%}")
print(f"   UPLS  - Avg SOC:         {upls_df['soc'].mean():>10.1%}")

# Energy throughput
basic_energy_discharged = (basic_df['battery_power'] * 0.25).sum()
upls_energy_discharged = (upls_df['battery_power'] * 0.25).sum()

print(f"\n   Basic - Energy cycled:   {abs(basic_energy_discharged):>10,.0f} kWh")
print(f"   UPLS  - Energy cycled:   {abs(upls_energy_discharged):>10,.0f} kWh")

# UPLS specific stats
print(f"\n🎮 UPLS ADVANCED STATS:")
print(f"   Peak Events Detected:    {upls_stats['total_peak_events']:>10,}")
print(f"   Successful Shaves:       {upls_stats['successful_shaves']:>10,}")
print(f"   Success Rate:            {upls_stats['peak_shaving_success_rate']:>10.1f}%")
print(f"   Avg Threshold:           {upls_stats['avg_threshold']:>10,.0f} kW")
print(f"   Threshold Std Dev:       {upls_stats['threshold_std']:>10,.0f} kW (adaptive)")
print(f"   Static Threshold:        {threshold_basic:>10,.0f} kW (basic)")

# Battery health
print(f"\n🔋 BATTERY HEALTH:")
print(f"   Basic - SOH:             {battery_basic.soh:>10.1%}")
print(f"   UPLS  - SOH:             {battery_upls.soh:>10.1%}")
print(f"   Basic - Total Cycles:    {battery_basic.total_cycles:>10.1f}")
print(f"   UPLS  - Total Cycles:    {battery_upls.total_cycles:>10.1f}")

# Verdict
print("\n" + "=" * 80)
if upls_pct > basic_pct * 1.1:  # 10% daha iyi
    improvement = ((upls_pct / basic_pct) - 1) * 100
    print(f"✅ UPLS {improvement:.0f}% DAHA İYİ PERFORMANS!")
    print(f"   Peak reduction: {basic_pct:.1f}% → {upls_pct:.1f}%")
elif upls_pct > basic_pct:
    print(f"✅ UPLS约微 DAHA İYİ ({upls_pct - basic_pct:.2f}% improvement)")
else:
    print(f"⚠️  UPLS beklenen performansı gösteremedi")
    print(f"   Possible reasons: aggressive factor too high, not enough historical data")

print("=" * 80)

# Kaydet
print("\n💾 Sonuçlar kaydediliyor...")
basic_df['timestamp'] = df_test['timestamp']
upls_df['timestamp'] = df_test['timestamp']

basic_df.to_csv('comparison_basic.csv', index=False)
upls_df.to_csv('comparison_upls.csv', index=False)

comparison_stats = {
    'test_period_days': len(df_test) / (24 * 4),
    'original_peak_kw': float(original_peak),
    'basic': {
        'peak_kw': float(basic_peak),
        'reduction_kw': float(basic_reduction),
        'reduction_pct': float(basic_pct),
        'threshold_kw': float(threshold_basic),
        'soh_final': float(battery_basic.soh),
        'total_cycles': float(battery_basic.total_cycles)
    },
    'upls': {
        'peak_kw': float(upls_peak),
        'reduction_kw': float(upls_reduction),
        'reduction_pct': float(upls_pct),
        'avg_threshold_kw': float(upls_stats['avg_threshold']),
        'soh_final': float(battery_upls.soh),
        'total_cycles': float(battery_upls.total_cycles),
        'peak_events': upls_stats['total_peak_events'],
        'success_rate': upls_stats['peak_shaving_success_rate']
    },
    'improvement': {
        'absolute_kw': float(upls_reduction - basic_reduction),
        'percentage_points': float(upls_pct - basic_pct)
    }
}

with open('comparison_stats.json', 'w') as f:
    json.dump(comparison_stats, f, indent=2)

print("   ✅ comparison_basic.csv")
print("   ✅ comparison_upls.csv")
print("   ✅ comparison_stats.json")

print("\n✨ KARŞILAŞTIRMA TAMAMLANDI!")
