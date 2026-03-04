"""
UPLS (Ultimate Peak Load Shaving) Controller
Advanced peak shaving algorithm with:
- Rolling window average
- Adaptive threshold
- Lookahead optimization
- SOC-aware decision making

Based on research: "A novel peak shaving algorithm for islanded microgrid 
using battery energy storage system"
"""

import numpy as np
import pandas as pd
from collections import deque


class UPLSController:
    """
    Ultimate Peak Load Shaving Controller
    
    Key Features:
    1. Rolling Average: 24-hour moving average for baseline
    2. Adaptive Threshold: Dynamically adjusts based on recent patterns
    3. Lookahead Window: Considers future load (4-8 hours)
    4. SOC Management: Ensures battery has energy when needed
    5. Weighting Factors: Multi-battery support with dynamic allocation
    """
    
    def __init__(self, config):
        """
        Args:
            config (dict): UPLS parameters
                - rolling_window_hours: Rolling average window (default: 24)
                - lookahead_hours: Future consideration window (default: 4)
                - adaptive_factor: How aggressive to shave (0.8-0.95)
                - soc_reserve_threshold: Min SOC to keep for future peaks
                - enable_forecast: Use forecast data if available
        """
        self.rolling_window_hours = config.get('rolling_window_hours', 24)
        self.lookahead_hours = config.get('lookahead_hours', 4)
        self.adaptive_factor = config.get('adaptive_factor', 0.85)
        self.soc_reserve = config.get('soc_reserve_threshold', 0.30)
        self.enable_forecast = config.get('enable_forecast', False)
        
        # Rolling window (15-min intervals -> 4 per hour)
        window_size = self.rolling_window_hours * 4
        self.load_history = deque(maxlen=window_size)
        
        # State tracking
        self.current_threshold = None
        self.peak_today = 0
        self.cycles_today = 0
        self.last_date = None
        
        # Decision log
        self.decision_log = []
        
        # Performance metrics
        self.total_peak_events = 0
        self.successful_shaves = 0
        
    def update_load_history(self, load_kw):
        """Add new load measurement to rolling window"""
        self.load_history.append(load_kw)
    
    def calculate_dynamic_threshold(self):
        """
        Calculate adaptive threshold based on rolling average
        
        Formula: threshold = rolling_avg + adaptive_factor * std_dev
        
        Returns:
            threshold (kW)
        """
        if len(self.load_history) < 10:  # Need minimum data
            return None
        
        loads = np.array(self.load_history)
        rolling_avg = np.mean(loads)
        rolling_std = np.std(loads)
        
        # Adaptive threshold using percentile (like basic controller)
        # adaptive_factor = 0.85 means 85th percentile
        # This gives comparable threshold to basic controller
        percentile = self.adaptive_factor * 100  # 0.85 -> 85th percentile
        threshold = np.percentile(loads, percentile)
        
        # Safety bounds
        min_threshold = rolling_avg * 1.05  # At least 5% above average
        max_threshold = np.max(loads) * 0.98  # At most 98% of historical peak
        
        threshold = np.clip(threshold, min_threshold, max_threshold)
        
        self.current_threshold = threshold
        return threshold
    
    def analyze_lookahead(self, forecast_load, current_idx=0):
        """
        Analyze upcoming load to predict peaks
        
        Args:
            forecast_load: Array of future loads (or None)
            current_idx: Current position in forecast
            
        Returns:
            dict with lookahead analysis
        """
        if forecast_load is None or not self.enable_forecast:
            return {
                'peak_expected': False,
                'peak_magnitude': 0,
                'time_to_peak': None
            }
        
        # Look ahead N hours
        lookahead_steps = self.lookahead_hours * 4  # 15-min intervals
        end_idx = min(current_idx + lookahead_steps, len(forecast_load))
        
        if end_idx <= current_idx:
            return {
                'peak_expected': False,
                'peak_magnitude': 0,
                'time_to_peak': None
            }
        
        future_loads = forecast_load[current_idx:end_idx]
        max_future_load = np.max(future_loads)
        max_idx = np.argmax(future_loads)
        
        # Is there a peak coming?
        threshold = self.current_threshold or np.mean(self.load_history)
        peak_expected = max_future_load > threshold * 1.1
        
        return {
            'peak_expected': peak_expected,
            'peak_magnitude': max_future_load,
            'time_to_peak': max_idx * 15,  # minutes
            'peak_threshold': threshold
        }
    
    def calculate_soc_target(self, battery, lookahead_info):
        """
        Determine target SOC based on upcoming peaks
        
        Strategy:
        - If peak expected soon: Ensure high SOC
        - If no peak expected: Can charge aggressively
        - If peak just passed: Recharge
        """
        current_soc = battery.soc
        
        if lookahead_info['peak_expected']:
            # Peak coming - need reserve
            time_to_peak = lookahead_info['time_to_peak']
            
            if time_to_peak < 60:  # Within 1 hour
                target_soc = 0.80  # High reserve
            elif time_to_peak < 120:  # Within 2 hours
                target_soc = 0.65  # Medium reserve
            else:
                target_soc = 0.55  # Normal reserve
        else:
            # No peak expected - can stay lower
            target_soc = 0.50
        
        return target_soc
    
    def decide_action(self, current_load_kw, battery, forecast_load=None, 
                     current_time=None, current_idx=0):
        """
        UPLS decision logic
        
        Args:
            current_load_kw: Current facility load
            battery: BatteryModel instance
            forecast_load: Array of future loads (optional)
            current_time: Current timestamp (optional)
            current_idx: Position in data sequence
            
        Returns:
            action dict with mode and power
        """
        # Update history
        self.update_load_history(current_load_kw)
        
        # Track daily stats
        if current_time is not None:
            current_date = current_time.date()
            if self.last_date != current_date:
                # New day
                self.peak_today = 0
                self.cycles_today = 0
                self.last_date = current_date
            
            self.peak_today = max(self.peak_today, current_load_kw)
        
        # Calculate dynamic threshold
        threshold = self.calculate_dynamic_threshold()
        
        if threshold is None:
            # Not enough data - conservative mode
            return {
                'mode': 'idle',
                'power_kw': 0,
                'reason': 'Insufficient history for UPLS',
                'threshold': None
            }
        
        # Lookahead analysis
        lookahead = self.analyze_lookahead(forecast_load, current_idx)
        
        # Target SOC based on forecast
        target_soc = self.calculate_soc_target(battery, lookahead)
        
        # CRITICAL SOC CHECKS
        if battery.soc < 0.15:
            # Emergency charge
            return {
                'mode': 'charge',
                'power_kw': battery.get_available_charge_power(),
                'reason': 'Emergency SOC recovery',
                'threshold': threshold,
                'target_soc': target_soc
            }
        
        # MAIN UPLS LOGIC
        
        # 1. PEAK SHAVING MODE (Primary objective)
        if current_load_kw > threshold:
            self.total_peak_events += 1
            
            # How much power needed to shave?
            power_needed = current_load_kw - threshold
            power_available = battery.get_available_discharge_power()
            
            # SOC check: Don't discharge if SOC too low AND peak expected soon
            if battery.soc < self.soc_reserve and lookahead['peak_expected']:
                if lookahead['time_to_peak'] < 30:  # Within 30 min
                    return {
                        'mode': 'idle',
                        'power_kw': 0,
                        'reason': f'SOC reserve for upcoming peak (T-{lookahead["time_to_peak"]}min)',
                        'threshold': threshold,
                        'target_soc': target_soc
                    }
            
            if power_available > 0:
                discharge_power = min(power_needed, power_available)
                
                # Multi-battery weighting (future: distribute across multiple batteries)
                # For now: Single battery uses 100%
                
                self.successful_shaves += 1
                
                return {
                    'mode': 'discharge',
                    'power_kw': discharge_power,
                    'reason': f'Peak shaving: {current_load_kw:.0f} > {threshold:.0f} kW',
                    'threshold': threshold,
                    'target_soc': target_soc,
                    'lookahead': lookahead
                }
            else:
                return {
                    'mode': 'idle',
                    'power_kw': 0,
                    'reason': 'Peak detected but battery depleted',
                    'threshold': threshold,
                    'target_soc': target_soc
                }
        
        # 2. SMART CHARGING MODE
        
        # Check if SOC below target
        if battery.soc < target_soc - 0.05:  # 5% hysteresis
            
            # Determine charge urgency
            if lookahead['peak_expected'] and lookahead['time_to_peak'] < 120:
                # Peak within 2 hours - charge aggressively
                charge_power = battery.get_available_charge_power()
                charge_urgency = 'urgent'
            else:
                # No immediate peak - moderate charging
                charge_power = min(
                    battery.get_available_charge_power(),
                    battery.power_kw * 0.6  # 60% of rated power
                )
                charge_urgency = 'normal'
            
            # Only charge during low load periods
            valley_threshold = threshold * 0.75
            
            if current_load_kw < valley_threshold and charge_power > 10:
                return {
                    'mode': 'charge',
                    'power_kw': charge_power,
                    'reason': f'SOC management ({charge_urgency}): {battery.soc:.1%} -> {target_soc:.1%}',
                    'threshold': threshold,
                    'target_soc': target_soc,
                    'lookahead': lookahead
                }
        
        # 3. IDLE MODE
        return {
            'mode': 'idle',
            'power_kw': 0,
            'reason': f'Optimal zone: load={current_load_kw:.0f}, threshold={threshold:.0f}, SOC={battery.soc:.1%}',
            'threshold': threshold,
            'target_soc': target_soc
        }
    
    def log_decision(self, timestamp, load_kw, action, battery_soc):
        """Log decision for analysis"""
        self.decision_log.append({
            'timestamp': timestamp,
            'load_kw': load_kw,
            'action_mode': action['mode'],
            'action_power_kw': action['power_kw'],
            'reason': action['reason'],
            'battery_soc': battery_soc,
            'threshold_kw': action.get('threshold'),
            'target_soc': action.get('target_soc')
        })
    
    def get_log_df(self):
        """Get decision log as DataFrame"""
        return pd.DataFrame(self.decision_log)
    
    def get_statistics(self):
        """Performance statistics"""
        if not self.decision_log:
            return {}
        
        df = self.get_log_df()
        
        success_rate = (
            self.successful_shaves / self.total_peak_events * 100
            if self.total_peak_events > 0 else 0
        )
        
        return {
            'total_decisions': len(df),
            'discharge_count': len(df[df['action_mode'] == 'discharge']),
            'charge_count': len(df[df['action_mode'] == 'charge']),
            'idle_count': len(df[df['action_mode'] == 'idle']),
            'total_peak_events': self.total_peak_events,
            'successful_shaves': self.successful_shaves,
            'peak_shaving_success_rate': success_rate,
            'avg_discharge_power': df[df['action_mode'] == 'discharge']['action_power_kw'].mean(),
            'avg_charge_power': df[df['action_mode'] == 'charge']['action_power_kw'].mean(),
            'avg_threshold': df['threshold_kw'].mean(),
            'threshold_std': df['threshold_kw'].std()
        }


# Test kodu
if __name__ == "__main__":
    from battery import BatteryModel
    
    print("🎯 UPLS Controller Test")
    print("=" * 70)
    
    # Batarya
    battery_config = {
        'capacity_kwh': 1000,
        'power_kw': 500,
        'efficiency': 0.95,
        'min_soc': 0.10,
        'max_soc': 0.90,
        'initial_soc': 0.50,
        'degradation_rate_per_cycle': 0.00017
    }
    battery = BatteryModel(battery_config)
    
    # UPLS Controller
    upls_config = {
        'rolling_window_hours': 24,
        'lookahead_hours': 4,
        'adaptive_factor': 0.85,
        'soc_reserve_threshold': 0.30,
        'enable_forecast': True
    }
    controller = UPLSController(upls_config)
    
    # Sentetik load profili (gerçekçi pattern)
    np.random.seed(42)
    hours = 48  # 2 gün
    load_profile = []
    
    for h in range(hours):
        # Gün/gece pattern
        if 6 <= h % 24 < 22:  # Gündüz
            base = 9000
            variation = 1500
        else:  # Gece
            base = 6000
            variation = 800
        
        # Peak saatler (10-12, 17-19)
        if (10 <= h % 24 <= 12) or (17 <= h % 24 <= 19):
            base += 2000
        
        # 15-dakikalık 4 veri noktası
        for _ in range(4):
            load = base + np.random.normal(0, variation)
            load_profile.append(max(load, 3000))
    
    load_profile = np.array(load_profile)
    
    print(f"Load profili: {len(load_profile)} veri noktası (2 gün)")
    print(f"Min: {load_profile.min():.0f} kW, Max: {load_profile.max():.0f} kW")
    print(f"Avg: {load_profile.mean():.0f} kW\n")
    
    # İlk 24 saat simülasyonu
    print("24 Saatlik Simülasyon Başlıyor...\n")
    
    results = []
    for idx in range(24 * 4):  # 24 saat x 4 (15-dakikalık)
        load = load_profile[idx]
        
        # UPLS karar
        action = controller.decide_action(
            current_load_kw=load,
            battery=battery,
            forecast_load=load_profile,
            current_idx=idx
        )
        
        # Batarya işlemi
        if action['mode'] == 'charge':
            actual = battery.charge(action['power_kw'], 0.25)
            battery_power = -actual
        elif action['mode'] == 'discharge':
            actual = battery.discharge(action['power_kw'], 0.25)
            battery_power = actual
        else:
            battery_power = 0
        
        net_load = load - battery_power
        
        results.append({
            'hour': idx / 4,
            'load': load,
            'net_load': net_load,
            'battery_power': battery_power,
            'soc': battery.soc,
            'threshold': action.get('threshold'),
            'mode': action['mode']
        })
        
        controller.log_decision(None, load, action, battery.soc)
        
        # Her 4 saatte bir rapor
        if (idx + 1) % 16 == 0:
            hour = (idx + 1) / 4
            print(f"Saat {hour:.0f}:")
            print(f"  Load: {load:.0f} kW -> Net: {net_load:.0f} kW")
            print(f"  Battery: {battery_power:+.0f} kW, SOC: {battery.soc:.1%}")
            print(f"  Threshold: {action.get('threshold', 0):.0f} kW")
            print(f"  Mode: {action['mode']}")
            print()
    
    # Sonuçlar
    results_df = pd.DataFrame(results)
    stats = controller.get_statistics()
    
    print("\n" + "=" * 70)
    print("📊 UPLS PERFORMANS RAPORU")
    print("=" * 70)
    print(f"\nOriginal Peak:        {results_df['load'].max():>8,.0f} kW")
    print(f"Reduced Peak:         {results_df['net_load'].max():>8,.0f} kW")
    reduction = results_df['load'].max() - results_df['net_load'].max()
    reduction_pct = (reduction / results_df['load'].max()) * 100
    print(f"Peak Reduction:       {reduction:>8,.0f} kW ({reduction_pct:.1f}%)")
    
    print(f"\nPeak Events:          {stats['total_peak_events']:>8}")
    print(f"Successful Shaves:    {stats['successful_shaves']:>8}")
    print(f"Success Rate:         {stats['peak_shaving_success_rate']:>8.1f}%")
    
    print(f"\nAvg Threshold:        {stats['avg_threshold']:>8,.0f} kW")
    print(f"Threshold Std Dev:    {stats['threshold_std']:>8,.0f} kW")
    
    print(f"\nDischarge Periods:    {stats['discharge_count']:>8}")
    print(f"Charge Periods:       {stats['charge_count']:>8}")
    print(f"Idle Periods:         {stats['idle_count']:>8}")
    
    print("\n✅ UPLS Controller Test Tamamlandı!")
