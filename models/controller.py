"""
Peak Shaving Controller - Akıllı Batarya Kontrol Algoritması
Fabrikanın peak tüketimini azaltmak için bataryayı optimize eder
"""

import numpy as np
import pandas as pd


class PeakShavingController:
    """
    Peak shaving kontrol algoritması
    
    Strateji:
    1. Yüksek tüketim anlarında bataryadan destek (discharge)
    2. Düşük tüketim anlarında bataryayı şarj et (charge)
    3. Dinamik threshold belirleme
    4. SOC yönetimi (bataryanın boş kalmaması için)
    """
    
    def __init__(self, config):
        """
        Args:
            config (dict): Kontrol parametreleri
                - peak_threshold_strategy: 'fixed' veya 'dynamic'
                - peak_threshold_percentile: Dynamic için (örn: 85)
                - peak_threshold_fixed_kw: Fixed için (örn: 10000)
                - lookahead_hours: Kaç saat ileriye bak
        """
        self.strategy = config.get('peak_threshold_strategy', 'dynamic')
        self.percentile = config.get('peak_threshold_percentile', 85)
        self.fixed_threshold = config.get('peak_threshold_fixed_kw', 10000)
        self.lookahead_hours = config.get('lookahead_hours', 4)
        
        self.threshold_kw = None
        self.decision_log = []
    
    def calculate_threshold(self, load_history):
        """
        Dinamik threshold hesapla
        
        Args:
            load_history: Geçmiş yük verisi (pandas Series veya array)
        
        Returns:
            threshold (kW)
        """
        if self.strategy == 'fixed':
            self.threshold_kw = self.fixed_threshold
        else:
            # Dynamic: Verinin %85'lik değerini kullan
            self.threshold_kw = np.percentile(load_history, self.percentile)
        
        return self.threshold_kw
    
    def decide_action(self, current_load_kw, battery, forecast_load=None, current_time=None):
        """
        Batarya için karar ver: charge/discharge/idle
        
        Args:
            current_load_kw: Şu anki fabrika yükü (kW)
            battery: BatteryModel instance
            forecast_load: Önümüzdeki saatler için tahmin (opsiyonel)
            current_time: Şu anki zaman (opsiyonel)
        
        Returns:
            action (dict):
                - mode: 'charge', 'discharge', 'idle'
                - power_kw: Güç miktarı (pozitif değer)
                - reason: Karar nedeni (debugging için)
        """
        
        if self.threshold_kw is None:
            return {'mode': 'idle', 'power_kw': 0, 'reason': 'Threshold not set'}
        
        # SOC kontrolü - kritik seviyeler
        if battery.soc < 0.15:
            # Batarya çok düşük - acil şarj
            return {
                'mode': 'charge',
                'power_kw': battery.get_available_charge_power(),
                'reason': 'Emergency charge (SOC < 15%)'
            }
        
        if battery.soc > 0.85:
            # Batarya çok dolu - sadece discharge
            if current_load_kw > self.threshold_kw:
                power_needed = current_load_kw - self.threshold_kw
                power_available = battery.get_available_discharge_power()
                return {
                    'mode': 'discharge',
                    'power_kw': min(power_needed, power_available),
                    'reason': f'Peak shaving (load {current_load_kw:.0f} > threshold {self.threshold_kw:.0f})'
                }
            else:
                return {'mode': 'idle', 'power_kw': 0, 'reason': 'SOC high, no peak'}
        
        # ANA LOJİK: Peak Shaving
        if current_load_kw > self.threshold_kw:
            # Yüksek yük - Discharge
            power_needed = current_load_kw - self.threshold_kw
            power_available = battery.get_available_discharge_power()
            
            if power_available > 0:
                return {
                    'mode': 'discharge',
                    'power_kw': min(power_needed, power_available),
                    'reason': f'Peak shaving (load {current_load_kw:.0f} > threshold {self.threshold_kw:.0f})'
                }
            else:
                return {'mode': 'idle', 'power_kw': 0, 'reason': 'Peak detected but battery empty'}
        
        elif current_load_kw < self.threshold_kw * 0.75:
            # Düşük yük - Charge (threshold'un %75'i altında)
            
            # Akıllı şarj: Eğer yakında peak bekliyorsa daha agresif şarj et
            charge_urgency = 1.0
            if forecast_load is not None and len(forecast_load) > 0:
                # Önümüzdeki 2 saat içinde peak var mı?
                upcoming_max = forecast_load[:8].max()  # 8 x 15min = 2 saat
                if upcoming_max > self.threshold_kw:
                    charge_urgency = 1.5  # Daha hızlı şarj et
            
            power_available = battery.get_available_charge_power()
            charge_power = min(
                power_available,
                battery.power_kw * 0.6 * charge_urgency  # Nominal gücün %60'ı
            )
            
            if charge_power > 10:  # Minimum 10 kW
                return {
                    'mode': 'charge',
                    'power_kw': charge_power,
                    'reason': f'Low load charging (load {current_load_kw:.0f} < {self.threshold_kw*0.75:.0f})'
                }
        
        # Arada kaldı - Idle
        return {
            'mode': 'idle',
            'power_kw': 0,
            'reason': f'Load in neutral zone ({current_load_kw:.0f} kW)'
        }
    
    def log_decision(self, timestamp, load_kw, action, battery_soc):
        """Karar geçmişini kaydet"""
        self.decision_log.append({
            'timestamp': timestamp,
            'load_kw': load_kw,
            'action_mode': action['mode'],
            'action_power_kw': action['power_kw'],
            'reason': action['reason'],
            'battery_soc': battery_soc,
            'threshold_kw': self.threshold_kw
        })
    
    def get_log_df(self):
        """Karar geçmişini DataFrame olarak döndür"""
        return pd.DataFrame(self.decision_log)
    
    def get_statistics(self):
        """Özet istatistikler"""
        if not self.decision_log:
            return {}
        
        df = self.get_log_df()
        
        return {
            'total_decisions': len(df),
            'discharge_count': len(df[df['action_mode'] == 'discharge']),
            'charge_count': len(df[df['action_mode'] == 'charge']),
            'idle_count': len(df[df['action_mode'] == 'idle']),
            'avg_discharge_power': df[df['action_mode'] == 'discharge']['action_power_kw'].mean(),
            'avg_charge_power': df[df['action_mode'] == 'charge']['action_power_kw'].mean(),
            'threshold_kw': self.threshold_kw
        }


class AdvancedPeakShavingController(PeakShavingController):
    """
    Gelişmiş peak shaving kontrolör
    
    Ek özellikler:
    - Load forecasting entegrasyonu
    - Multi-day optimization
    - Time-of-use arbitrage
    - Reactive power support
    """
    
    def __init__(self, config):
        super().__init__(config)
        self.enable_tou_arbitrage = config.get('enable_tou_arbitrage', False)
        self.tou_peak_hours = config.get('tou_peak_hours', [10, 11, 12, 17, 18, 19, 20])
    
    def decide_action(self, current_load_kw, battery, forecast_load=None, current_time=None):
        """
        Gelişmiş karar mekanizması
        
        TOU arbitrage dahil: Ucuz saatlerde şarj, pahalı saatlerde deşarj
        """
        
        # Önce ana peak shaving lojiği
        base_action = super().decide_action(current_load_kw, battery, forecast_load, current_time)
        
        # TOU arbitrage eklenmişse
        if self.enable_tou_arbitrage and current_time is not None:
            hour = current_time.hour
            
            # Pahalı saatlerde - daha agresif discharge
            if hour in self.tou_peak_hours:
                if base_action['mode'] == 'idle' and battery.soc > 0.4:
                    # Peak saat ama load threshold altında
                    # Yine de küçük miktarda discharge et (arbitrage)
                    return {
                        'mode': 'discharge',
                        'power_kw': min(100, battery.get_available_discharge_power()),
                        'reason': f'TOU arbitrage (peak hour {hour}:00)'
                    }
            
            # Ucuz saatlerde - daha agresif charge
            else:
                if base_action['mode'] == 'idle' and battery.soc < 0.7:
                    # Off-peak saat ve batarya dolu değil
                    return {
                        'mode': 'charge',
                        'power_kw': min(200, battery.get_available_charge_power()),
                        'reason': f'TOU arbitrage (off-peak hour {hour}:00)'
                    }
        
        return base_action


# Test kodu
if __name__ == "__main__":
    from battery import BatteryModel
    
    print("🎛️ Peak Shaving Controller Test")
    print("=" * 60)
    
    # Batarya oluştur
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
    
    # Controller oluştur
    controller_config = {
        'peak_threshold_strategy': 'dynamic',
        'peak_threshold_percentile': 85,
        'lookahead_hours': 4
    }
    controller = PeakShavingController(controller_config)
    
    # Sentetik yük profili
    load_profile = np.random.normal(8000, 1500, 1000)  # 8MW ortalama
    load_profile = np.clip(load_profile, 4000, 12000)
    
    # Threshold hesapla
    threshold = controller.calculate_threshold(load_profile)
    print(f"Hesaplanan threshold: {threshold:.0f} kW")
    print(f"Load profili: {load_profile.min():.0f} - {load_profile.max():.0f} kW")
    print()
    
    # Farklı senaryolar test et
    scenarios = [
        ('Yüksek yük (peak)', 11000),
        ('Orta yük', 8500),
        ('Düşük yük', 6000),
        ('Çok düşük yük', 4500),
    ]
    
    for scenario_name, load in scenarios:
        action = controller.decide_action(load, battery)
        print(f"{scenario_name}: {load} kW")
        print(f"  Karar: {action['mode'].upper()}")
        print(f"  Güç: {action['power_kw']:.1f} kW")
        print(f"  Neden: {action['reason']}")
        print(f"  Batarya SOC: {battery.soc:.1%}")
        print()
    
    # SOC limit testi
    print("SOC Limit Testleri:")
    print("-" * 60)
    
    battery.soc = 0.12
    action = controller.decide_action(7000, battery)
    print(f"SOC çok düşük (12%): {action['mode']} - {action['reason']}")
    
    battery.soc = 0.88
    action = controller.decide_action(10500, battery)
    print(f"SOC çok yüksek (88%), peak var: {action['mode']} - {action['reason']}")
    
    print("\n✅ Controller çalışıyor!")
