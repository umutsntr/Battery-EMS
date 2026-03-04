"""
Peak Shaving Simulator - Ana Simülasyon Motoru
Gerçek veri üzerinde peak shaving simülasyonu çalıştırır
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path
import sys

# Models import
sys.path.append(str(Path(__file__).parent.parent))
from models.battery import BatteryModel
from models.controller import PeakShavingController


class PeakShavingSimulator:
    """
    Peak shaving simülasyon motoru
    
    İş akışı:
    1. Elektrik tüketim verisini yükle
    2. Batarya ve controller oluştur
    3. Her zaman adımında:
       - Controller kararı al
       - Bataryayı güncelle
       - Sonuçları kaydet
    4. Analiz yap ve raporla
    """
    
    def __init__(self, config_path='config/config.json'):
        """
        Args:
            config_path: Konfigürasyon dosyası yolu
        """
        # Config yükle
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        self.battery = None
        self.controller = None
        self.results = None
    
    def load_data(self, data_path):
        """
        Elektrik tüketim verisini yükle
        
        Args:
            data_path: CSV dosya yolu
        
        Returns:
            DataFrame
        """
        df = pd.read_csv(data_path)
        
        # Sütun isimlerini normalize et
        df.columns = df.columns.str.strip()
        
        # Timestamp parse et
        if 'Tarih_Saat' in df.columns:
            df['timestamp'] = pd.to_datetime(df['Tarih_Saat'])
            df['load_kw'] = df['Guc_kW']
        elif 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            if 'total_kw' in df.columns:
                df['load_kw'] = df['total_kw']
        else:
            raise ValueError("Timestamp sütunu bulunamadı")
        
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        print(f"✅ {len(df):,} satır veri yüklendi")
        print(f"   Dönem: {df['timestamp'].min()} - {df['timestamp'].max()}")
        print(f"   Load: {df['load_kw'].min():.0f} - {df['load_kw'].max():.0f} kW")
        
        return df
    
    def run(self, data_path, verbose=True):
        """
        Simülasyonu çalıştır
        
        Args:
            data_path: Elektrik verisi dosya yolu
            verbose: Detaylı çıktı
        
        Returns:
            results (dict): Simülasyon sonuçları
        """
        print("\n🚀 Peak Shaving Simülasyonu Başlatılıyor...")
        print("=" * 70)
        
        # 1. Veriyi yükle
        print("\n1️⃣ Veri yükleniyor...")
        df = self.load_data(data_path)
        
        # 2. Batarya ve controller oluştur
        print("\n2️⃣ Sistem oluşturuluyor...")
        self.battery = BatteryModel(self.config['battery'])
        self.controller = PeakShavingController(self.config['simulation'])
        
        print(f"   Batarya: {self.battery.capacity_kwh} kWh / {self.battery.power_kw} kW")
        print(f"   SOC limitleri: {self.battery.min_soc:.0%} - {self.battery.max_soc:.0%}")
        
        # 3. Threshold hesapla
        print("\n3️⃣ Peak threshold hesaplanıyor...")
        threshold = self.controller.calculate_threshold(df['load_kw'])
        print(f"   Threshold: {threshold:.0f} kW ({self.controller.strategy})")
        print(f"   Ortalama yük: {df['load_kw'].mean():.0f} kW")
        print(f"   Peak yük: {df['load_kw'].max():.0f} kW")
        
        # 4. Simülasyon
        print("\n4️⃣ Simülasyon çalışıyor...")
        print("   (Bu 20-30 saniye sürebilir)")
        
        results_list = []
        interval_hours = self.config['simulation']['interval_minutes'] / 60
        
        for idx, row in df.iterrows():
            timestamp = row['timestamp']
            load_kw = row['load_kw']
            
            # Controller kararı
            action = self.controller.decide_action(
                current_load_kw=load_kw,
                battery=self.battery,
                current_time=timestamp
            )
            
            # Batarya işlemi
            if action['mode'] == 'charge':
                actual_power = self.battery.charge(action['power_kw'], interval_hours)
                battery_power = -actual_power  # Negatif = şarj
            elif action['mode'] == 'discharge':
                actual_power = self.battery.discharge(action['power_kw'], interval_hours)
                battery_power = actual_power  # Pozitif = deşarj
            else:
                battery_power = 0
            
            # Net yük (şebekeden çekilen)
            net_load_kw = load_kw - battery_power
            
            # Kaydet
            results_list.append({
                'timestamp': timestamp,
                'original_load_kw': load_kw,
                'battery_power_kw': battery_power,
                'net_load_kw': net_load_kw,
                'battery_soc': self.battery.soc,
                'action_mode': action['mode']
            })
            
            # Log
            self.battery.log_state(timestamp)
            self.controller.log_decision(
                timestamp, load_kw, action, self.battery.soc
            )
            
            # Progress
            if verbose and idx % 5000 == 0:
                progress = (idx / len(df)) * 100
                print(f"   İlerleme: {progress:.0f}%", end='\r')
        
        # Degradation güncelle
        self.battery.update_degradation()
        
        print("\n   ✅ Simülasyon tamamlandı!")
        
        # 5. Sonuçları analiz et
        print("\n5️⃣ Sonuçlar analiz ediliyor...")
        self.results = pd.DataFrame(results_list)
        analysis = self._analyze_results(df, self.results)
        
        return {
            'dataframe': self.results,
            'analysis': analysis,
            'battery_stats': self.battery.get_statistics(),
            'controller_stats': self.controller.get_statistics()
        }
    
    def _analyze_results(self, original_df, results_df):
        """Sonuçları analiz et"""
        
        # Peak reduction
        original_peak = original_df['load_kw'].max()
        reduced_peak = results_df['net_load_kw'].max()
        peak_reduction_kw = original_peak - reduced_peak
        peak_reduction_pct = (peak_reduction_kw / original_peak) * 100
        
        # Energy metrics
        total_energy_charged = abs(
            results_df[results_df['battery_power_kw'] < 0]['battery_power_kw'].sum()
        ) * (self.config['simulation']['interval_minutes'] / 60)
        
        total_energy_discharged = results_df[
            results_df['battery_power_kw'] > 0
        ]['battery_power_kw'].sum() * (self.config['simulation']['interval_minutes'] / 60)
        
        # Operational metrics
        charge_periods = len(results_df[results_df['action_mode'] == 'charge'])
        discharge_periods = len(results_df[results_df['action_mode'] == 'discharge'])
        idle_periods = len(results_df[results_df['action_mode'] == 'idle'])
        
        total_periods = len(results_df)
        
        analysis = {
            # Peak reduction
            'original_peak_kw': float(original_peak),
            'reduced_peak_kw': float(reduced_peak),
            'peak_reduction_kw': float(peak_reduction_kw),
            'peak_reduction_pct': float(peak_reduction_pct),
            
            # Energy
            'total_energy_charged_kwh': float(total_energy_charged),
            'total_energy_discharged_kwh': float(total_energy_discharged),
            'round_trip_efficiency': float(
                total_energy_discharged / total_energy_charged
                if total_energy_charged > 0 else 0
            ),
            
            # Operations
            'charge_periods': int(charge_periods),
            'discharge_periods': int(discharge_periods),
            'idle_periods': int(idle_periods),
            'charge_time_pct': float((charge_periods / total_periods) * 100),
            'discharge_time_pct': float((discharge_periods / total_periods) * 100),
            
            # Battery
            'final_soc': float(results_df['battery_soc'].iloc[-1]),
            'avg_soc': float(results_df['battery_soc'].mean()),
            'min_soc': float(results_df['battery_soc'].min()),
            'max_soc': float(results_df['battery_soc'].max()),
        }
        
        # Print summary
        print("\n" + "=" * 70)
        print("📊 SİMÜLASYON SONUÇLARI")
        print("=" * 70)
        print(f"\n🎯 PEAK SHAVING PERFORMANSI:")
        print(f"   Orijinal peak:     {analysis['original_peak_kw']:>8,.0f} kW")
        print(f"   Azaltılmış peak:   {analysis['reduced_peak_kw']:>8,.0f} kW")
        print(f"   Peak azaltımı:     {analysis['peak_reduction_kw']:>8,.0f} kW ({analysis['peak_reduction_pct']:.1f}%)")
        
        print(f"\n⚡ ENERJİ METRİKLERİ:")
        print(f"   Şarj edilen:       {analysis['total_energy_charged_kwh']:>8,.0f} kWh")
        print(f"   Deşarj edilen:     {analysis['total_energy_discharged_kwh']:>8,.0f} kWh")
        print(f"   Round-trip eff:    {analysis['round_trip_efficiency']:>8.1%}")
        
        print(f"\n🔋 BATARYA KULLANIMI:")
        print(f"   Şarj süresi:       {analysis['charge_time_pct']:>8.1f}%")
        print(f"   Deşarj süresi:     {analysis['discharge_time_pct']:>8.1f}%")
        print(f"   Ortalama SOC:      {analysis['avg_soc']:>8.1%}")
        print(f"   SOC aralığı:       {analysis['min_soc']:.1%} - {analysis['max_soc']:.1%}")
        
        return analysis
    
    def save_results(self, output_dir='outputs'):
        """Sonuçları kaydet"""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        # DataFrame
        self.results.to_csv(output_path / 'simulation_results.csv', index=False)
        
        # Battery history
        battery_history = self.battery.get_history_df()
        battery_history.to_csv(output_path / 'battery_history.csv', index=False)
        
        # Controller log
        controller_log = self.controller.get_log_df()
        controller_log.to_csv(output_path / 'controller_log.csv', index=False)
        
        print(f"\n💾 Sonuçlar kaydedildi: {output_path}/")


# Ana çalıştırma
if __name__ == "__main__":
    # Simülatör oluştur
    sim = PeakShavingSimulator(config_path='config/config.json')
    
    # Sentetik veri ile çalıştır
    results = sim.run('data/synthetic/elektrik_tuketim.csv')
    
    # Sonuçları kaydet
    sim.save_results('outputs')
    
    print("\n" + "=" * 70)
    print("✅ SİMÜLASYON BAŞARILI!")
    print("=" * 70)
    print("\n📂 Oluşturulan dosyalar:")
    print("   outputs/simulation_results.csv  - Ana sonuçlar")
    print("   outputs/battery_history.csv     - Batarya geçmişi")
    print("   outputs/controller_log.csv      - Kontrol kararları")
    print("\n💡 Grafikler için:")
    print("   python analysis/visualization.py")
