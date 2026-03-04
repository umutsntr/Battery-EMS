"""
Battery Model - Batarya Sistemi Simülasyonu
LFP batarya dinamiklerini modelleyen sınıf
"""

import numpy as np
import pandas as pd


class BatteryModel:
    """
    Batarya Enerji Depolama Sistemi (BESS) modeli
    
    Özellikler:
    - SOC (State of Charge) tracking
    - Power limits (C-rate kısıtları)
    - Round-trip efficiency
    - Degradation modeling
    - Cycle counting
    """
    
    def __init__(self, config):
        """
        Args:
            config (dict): Batarya parametreleri
                - capacity_kwh: Kapasite (kWh)
                - power_kw: Nominal güç (kW)
                - efficiency: Round-trip verimlilik (0-1)
                - min_soc: Minimum SOC (0-1)
                - max_soc: Maximum SOC (0-1)
                - initial_soc: Başlangıç SOC (0-1)
                - degradation_rate_per_cycle: Cycle başına kapasite kaybı
        """
        self.capacity_kwh = config['capacity_kwh']
        self.power_kw = config['power_kw']
        self.efficiency = config['efficiency']
        self.min_soc = config['min_soc']
        self.max_soc = config['max_soc']
        self.soc = config['initial_soc']
        self.degradation_rate = config['degradation_rate_per_cycle']
        
        # İstatistikler
        self.total_energy_charged = 0  # kWh
        self.total_energy_discharged = 0  # kWh
        self.total_cycles = 0
        self.soh = 1.0  # State of Health (1.0 = yeni)
        
        # Log
        self.history = []
    
    def get_usable_capacity(self):
        """Kullanılabilir kapasite (SOC limitleri dahilinde)"""
        return self.capacity_kwh * (self.max_soc - self.min_soc) * self.soh
    
    def get_available_charge_power(self):
        """Şu anki durumda ne kadar şarj gücü kullanılabilir (kW)"""
        if self.soc >= self.max_soc:
            return 0
        
        # Güç limiti
        max_power = min(self.power_kw, self.power_kw * self.soh)
        
        # SOC limiti (max_soc'a ulaşmamak için)
        energy_to_max = (self.max_soc - self.soc) * self.capacity_kwh * self.soh
        
        return min(max_power, energy_to_max * 4)  # 4 = 15 min -> saat çevirici
    
    def get_available_discharge_power(self):
        """Şu anki durumda ne kadar deşarj gücü kullanılabilir (kW)"""
        if self.soc <= self.min_soc:
            return 0
        
        # Güç limiti
        max_power = min(self.power_kw, self.power_kw * self.soh)
        
        # SOC limiti (min_soc'a inmemek için)
        energy_to_min = (self.soc - self.min_soc) * self.capacity_kwh * self.soh
        
        return min(max_power, energy_to_min * 4)  # 4 = 15 min -> saat çevirici
    
    def charge(self, power_kw, duration_hours):
        """
        Bataryayı şarj et
        
        Args:
            power_kw: Şarj gücü (kW) - pozitif değer
            duration_hours: Süre (saat) - tipik 0.25 (15 dakika)
        
        Returns:
            actual_power: Gerçekte kullanılan güç (kW)
        """
        # Güç limiti kontrol
        available_power = self.get_available_charge_power()
        actual_power = min(power_kw, available_power)
        
        if actual_power <= 0:
            return 0
        
        # Enerji hesapla (verimlilik dahil)
        energy_in = actual_power * duration_hours
        energy_stored = energy_in * np.sqrt(self.efficiency)  # Şarj verimi
        
        # SOC güncelle
        soc_increase = energy_stored / (self.capacity_kwh * self.soh)
        self.soc = min(self.soc + soc_increase, self.max_soc)
        
        # İstatistik güncelle
        self.total_energy_charged += energy_in
        
        return actual_power
    
    def discharge(self, power_kw, duration_hours):
        """
        Bataryayı deşarj et
        
        Args:
            power_kw: Deşarj gücü (kW) - pozitif değer
            duration_hours: Süre (saat) - tipik 0.25 (15 dakika)
        
        Returns:
            actual_power: Gerçekte sağlanan güç (kW)
        """
        # Güç limiti kontrol
        available_power = self.get_available_discharge_power()
        actual_power = min(power_kw, available_power)
        
        if actual_power <= 0:
            return 0
        
        # Enerji hesapla (verimlilik dahil)
        energy_out = actual_power * duration_hours
        energy_from_storage = energy_out / np.sqrt(self.efficiency)  # Deşarj verimi
        
        # SOC güncelle
        soc_decrease = energy_from_storage / (self.capacity_kwh * self.soh)
        self.soc = max(self.soc - soc_decrease, self.min_soc)
        
        # İstatistik güncelle
        self.total_energy_discharged += energy_out
        
        return actual_power
    
    def update_degradation(self):
        """
        Degradation (kapasite kaybı) güncelle
        
        Basit model: Her cycle'da sabit oranda kaybediyor
        Gerçek hayat: Sıcaklık, DOD, C-rate'e bağlı - sonra eklenebilir
        """
        # Cycle sayısını hesapla (throughput bazlı)
        throughput_kwh = (self.total_energy_charged + self.total_energy_discharged) / 2
        cycles = throughput_kwh / self.capacity_kwh
        
        # SOH güncelle
        self.soh = max(1.0 - (cycles * self.degradation_rate), 0.8)  # Minimum %80
        
        self.total_cycles = cycles
    
    def log_state(self, timestamp):
        """Mevcut durumu kaydet"""
        self.history.append({
            'timestamp': timestamp,
            'soc': self.soc,
            'soh': self.soh,
            'available_charge_power': self.get_available_charge_power(),
            'available_discharge_power': self.get_available_discharge_power(),
            'total_cycles': self.total_cycles
        })
    
    def get_history_df(self):
        """Geçmiş kayıtları DataFrame olarak döndür"""
        return pd.DataFrame(self.history)
    
    def get_statistics(self):
        """Özet istatistikler"""
        return {
            'capacity_kwh': self.capacity_kwh,
            'power_kw': self.power_kw,
            'current_soc': self.soc,
            'current_soh': self.soh,
            'total_energy_charged_kwh': self.total_energy_charged,
            'total_energy_discharged_kwh': self.total_energy_discharged,
            'total_cycles': self.total_cycles,
            'round_trip_efficiency': (
                self.total_energy_discharged / self.total_energy_charged 
                if self.total_energy_charged > 0 else 0
            ),
            'energy_throughput_kwh': (
                self.total_energy_charged + self.total_energy_discharged
            ) / 2
        }
    
    def reset(self):
        """Bataryayı başlangıç durumuna getir"""
        self.soc = 0.50  # %50
        self.soh = 1.0
        self.total_energy_charged = 0
        self.total_energy_discharged = 0
        self.total_cycles = 0
        self.history = []


# Test kodu
if __name__ == "__main__":
    # Örnek konfigürasyon
    config = {
        'capacity_kwh': 1000,
        'power_kw': 500,
        'efficiency': 0.95,
        'min_soc': 0.10,
        'max_soc': 0.90,
        'initial_soc': 0.50,
        'degradation_rate_per_cycle': 0.00017
    }
    
    battery = BatteryModel(config)
    
    print("🔋 Batarya Modeli Test")
    print("=" * 50)
    print(f"Kapasite: {battery.capacity_kwh} kWh")
    print(f"Güç: {battery.power_kw} kW")
    print(f"Başlangıç SOC: {battery.soc:.1%}")
    print()
    
    # Test 1: Şarj
    print("Test 1: 15 dakika 300 kW şarj")
    actual = battery.charge(300, 0.25)
    print(f"  Gerçek güç: {actual:.1f} kW")
    print(f"  Yeni SOC: {battery.soc:.1%}")
    print()
    
    # Test 2: Deşarj
    print("Test 2: 15 dakika 400 kW deşarj")
    actual = battery.discharge(400, 0.25)
    print(f"  Gerçek güç: {actual:.1f} kW")
    print(f"  Yeni SOC: {battery.soc:.1%}")
    print()
    
    # Test 3: Limit testi (SOC max'a yakın)
    print("Test 3: SOC limitlerini test et")
    battery.soc = 0.88
    print(f"  Mevcut SOC: {battery.soc:.1%}")
    print(f"  Kullanılabilir şarj gücü: {battery.get_available_charge_power():.1f} kW")
    actual = battery.charge(500, 0.25)
    print(f"  500 kW şarj isteği -> Gerçek: {actual:.1f} kW")
    print(f"  Yeni SOC: {battery.soc:.1%}")
    print()
    
    # Test 4: Degradation
    print("Test 4: 100 cycle sonrası degradation")
    battery.reset()
    for i in range(400):  # 400 x 0.25 saat = 100 saat cycling
        battery.charge(500, 0.25)
        battery.discharge(500, 0.25)
    battery.update_degradation()
    
    stats = battery.get_statistics()
    print(f"  Toplam cycle: {stats['total_cycles']:.1f}")
    print(f"  SOH: {stats['current_soh']:.1%}")
    print(f"  Round-trip efficiency: {stats['round_trip_efficiency']:.1%}")
    print(f"  Energy throughput: {stats['energy_throughput_kwh']:.0f} kWh")
    
    print("\n✅ Batarya modeli çalışıyor!")
