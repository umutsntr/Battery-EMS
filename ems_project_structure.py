"""
EMS Peak Shaving - Proje Yapısı Oluşturucu
Çimento fabrikası için sentetik veri üretir ve proje klasör yapısını hazırlar
"""

import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import json

def create_project_structure():
    """Proje klasör yapısını oluştur"""
    folders = [
        'data/raw',
        'data/processed',
        'data/synthetic',
        'models',
        'simulation',
        'analysis',
        'notebooks',
        'config',
        'outputs/reports',
        'outputs/plots'
    ]
    
    for folder in folders:
        os.makedirs(folder, exist_ok=True)
        print(f"✓ {folder} oluşturuldu")
    
    print("\n✅ Proje yapısı hazır!")

def generate_cement_factory_data(
    start_date='2023-01-01',
    end_date='2024-01-01',
    interval_minutes=15
):
    """
    Gerçekçi çimento fabrikası elektrik tüketim verisi üret
    
    Özellikler:
    - Fırın: 24/7 sürekli (3500-4000 kW)
    - Hammadde değirmeni: Vardiya saatlerinde (2500-3000 kW)
    - Çimento değirmeni: Aralıklı (2000-3500 kW)
    - Yardımcı sistemler: Sürekli (1000-1500 kW)
    - Vardiya değişimleri: Sabah 08:00, Akşam 16:00, Gece 00:00
    - Hafta sonu: %70 kapasite
    """
    
    # Zaman serisi oluştur
    date_range = pd.date_range(
        start=start_date,
        end=end_date,
        freq=f'{interval_minutes}min'
    )
    
    # Boş dataframe
    df = pd.DataFrame(index=date_range)
    df['timestamp'] = df.index
    
    # Temel bileşenler
    kiln_power = []  # Fırın
    raw_mill_power = []  # Hammadde değirmeni
    cement_mill_power = []  # Çimento değirmeni
    auxiliary_power = []  # Yardımcı sistemler
    
    for dt in date_range:
        hour = dt.hour
        minute = dt.minute
        day_of_week = dt.dayofweek  # 0=Pazartesi, 6=Pazar
        
        # FIRIN - 24/7 sürekli, hafif dalgalanma
        kiln_base = 3750
        kiln_variation = np.random.normal(0, 150)
        kiln = kiln_base + kiln_variation
        
        # HAMMADDE DEĞİRMENİ - Vardiya saatlerinde
        if 6 <= hour < 22:  # Gündüz vardiyaları
            if day_of_week < 5:  # Hafta içi
                raw_mill = np.random.uniform(2500, 3000)
            else:  # Hafta sonu
                raw_mill = np.random.uniform(1800, 2200)
        else:  # Gece
            if day_of_week < 5:
                raw_mill = np.random.uniform(2000, 2500)
            else:
                raw_mill = np.random.uniform(1000, 1500)
        
        # ÇİMENTO DEĞİRMENİ - Aralıklı çalışma (saat başında yüksek ihtimal)
        if minute < 5:  # Saat başı start-up spike
            cement_mill = np.random.uniform(3000, 3500)
        elif minute < 40:  # Normal çalışma
            if np.random.random() > 0.3:  # %70 çalışma ihtimali
                cement_mill = np.random.uniform(2500, 3200)
            else:  # Durmuş
                cement_mill = np.random.uniform(200, 500)
        else:  # Ramp down
            cement_mill = np.random.uniform(1500, 2000)
        
        # Hafta sonu azalt
        if day_of_week >= 5:
            cement_mill *= 0.6
        
        # YARDIMCI SİSTEMLER - Sürekli, hafif değişken
        auxiliary = np.random.uniform(1000, 1500)
        
        # VARDİYA DEĞİŞİMİ SPİKE'LARI (tüm ekipman aynı anda start)
        if hour in [8, 16, 0] and minute < 15:
            # Vardiya başlangıcı - kısa süreli spike
            raw_mill *= 1.3
            cement_mill *= 1.2
            auxiliary *= 1.15
        
        # BAKIM DURUŞLARI (her ayın ilk Pazarı)
        if day_of_week == 6 and 1 <= dt.day <= 7:  # İlk Pazar
            # Planlı bakım - sadece fırın çalışır
            raw_mill *= 0.1
            cement_mill *= 0.1
            auxiliary *= 0.5
        
        # Kaydet
        kiln_power.append(kiln)
        raw_mill_power.append(raw_mill)
        cement_mill_power.append(cement_mill)
        auxiliary_power.append(auxiliary)
    
    # Dataframe'e ekle
    df['kiln_kw'] = kiln_power
    df['raw_mill_kw'] = raw_mill_power
    df['cement_mill_kw'] = cement_mill_power
    df['auxiliary_kw'] = auxiliary_power
    df['total_kw'] = df['kiln_kw'] + df['raw_mill_kw'] + df['cement_mill_kw'] + df['auxiliary_kw']
    
    # Mevsimsel etki (yazın klima +5-10%)
    month = df.index.month
    seasonal_factor = 1 + 0.08 * np.sin((month - 1) * np.pi / 6)  # Temmuz'da peak
    df['total_kw'] = df['total_kw'] * seasonal_factor
    
    # Gerçekçi noise ekle
    df['total_kw'] = df['total_kw'] + np.random.normal(0, 100, len(df))
    
    # Negatif değerleri düzelt
    df['total_kw'] = df['total_kw'].clip(lower=0)
    
    return df

def generate_production_data(electricity_df):
    """Üretim verisi üret (günlük bazda)"""
    
    daily = electricity_df.resample('D', on='timestamp').agg({
        'total_kw': 'mean',
        'kiln_kw': 'mean'
    })
    
    # Üretim miktarı yaklaşık fırın gücü ile orantılı
    # Çimento fabrikası: ~1.2-1.5 ton/MWh fırın enerjisi
    daily['production_ton'] = (daily['kiln_kw'] * 24 / 1000) * 1.3
    daily['production_ton'] = daily['production_ton'] + np.random.normal(0, 50, len(daily))
    daily['production_ton'] = daily['production_ton'].clip(lower=0)
    
    # Fırın durumu
    daily['kiln_status'] = 'Çalışıyor'
    daily.loc[daily['kiln_kw'] < 2000, 'kiln_status'] = 'Durdu'
    
    # Vardiya
    daily['day_of_week'] = daily.index.dayofweek
    daily['shift_type'] = daily['day_of_week'].map({
        0: '3 Vardiya', 1: '3 Vardiya', 2: '3 Vardiya', 
        3: '3 Vardiya', 4: '3 Vardiya', 5: '2 Vardiya', 6: 'Bakım'
    })
    
    return daily[['production_ton', 'kiln_status', 'shift_type']]

def generate_tariff_structure():
    """Türkiye sanayi elektrik tarifesi yapısı"""
    
    tariff = {
        # Gerçekçi Türkiye değerleri (2024)
        'demand_charge_tl_per_kw': 180,  # TL/kW/ay (kapasite bedeli)
        'energy_charge_tl_per_kwh': 2.5,  # TL/kWh (ortalama)
        
        # Time-of-use (varsa)
        'tou_peak_hours': [10, 11, 12, 13, 14, 17, 18, 19, 20],  # Puant saatler
        'tou_peak_multiplier': 1.3,
        'tou_offpeak_multiplier': 0.8,
        
        # Reaktif enerji (power factor < 0.9 ise ceza)
        'reactive_penalty_threshold': 0.90,
        'reactive_penalty_tl_per_kvarh': 1.2,
        
        # Sözleşme gücü
        'contract_demand_kw': 12000,
        
        # Dağıtım bedeli (sabit, batarya ile azaltılamaz)
        'distribution_charge_tl_per_kwh': 0.45,
        
        # USD/TRY kur (finansal hesaplar için)
        'usd_try_rate': 32.5
    }
    
    return tariff

def save_synthetic_data(electricity_df, production_df, tariff):
    """Sentetik veriyi dosyalara kaydet"""
    
    # Elektrik verisi - sadece müşteriden gelecek format
    output_electric = electricity_df[['timestamp', 'total_kw']].copy()
    output_electric.columns = ['Tarih_Saat', 'Guc_kW']
    output_electric.to_csv('data/synthetic/elektrik_tuketim.csv', index=False)
    print("✓ elektrik_tuketim.csv oluşturuldu")
    
    # Detaylı veri (internal use - gerçek fabrikada olmayacak)
    electricity_df.to_csv('data/synthetic/elektrik_detayli.csv', index=False)
    print("✓ elektrik_detayli.csv oluşturuldu (ekipman bazlı - internal)")
    
    # Üretim verisi
    production_df.to_csv('data/synthetic/uretim_verisi.csv')
    print("✓ uretim_verisi.csv oluşturuldu")
    
    # Tarife yapısı
    with open('data/synthetic/tarife_yapisi.json', 'w', encoding='utf-8') as f:
        json.dump(tariff, f, indent=2, ensure_ascii=False)
    print("✓ tarife_yapisi.json oluşturuldu")
    
    # Özet istatistikler
    stats = {
        'veri_donemi': f"{electricity_df['timestamp'].min()} - {electricity_df['timestamp'].max()}",
        'toplam_gun': len(electricity_df) / (24 * 4),  # 15-dakikalık interval
        'ortalama_guc_kw': float(electricity_df['total_kw'].mean()),
        'peak_guc_kw': float(electricity_df['total_kw'].max()),
        'min_guc_kw': float(electricity_df['total_kw'].min()),
        'toplam_tuketim_mwh': float(electricity_df['total_kw'].sum() * 0.25 / 1000),  # 15 min = 0.25 saat
        'yillik_uretim_ton': float(production_df['production_ton'].sum())
    }
    
    with open('data/synthetic/veri_ozeti.json', 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    print("✓ veri_ozeti.json oluşturuldu")
    
    print(f"\n📊 VERİ ÖZETİ:")
    print(f"   Dönem: {stats['veri_donemi']}")
    print(f"   Ortalama güç: {stats['ortalama_guc_kw']:.0f} kW")
    print(f"   Peak güç: {stats['peak_guc_kw']:.0f} kW")
    print(f"   Yıllık tüketim: {stats['toplam_tuketim_mwh']:.0f} MWh")
    print(f"   Yıllık üretim: {stats['yillik_uretim_ton']:.0f} ton çimento")

def create_config_file():
    """Konfigürasyon dosyası oluştur"""
    
    config = {
        'battery': {
            'capacity_kwh': 1000,
            'power_kw': 500,
            'efficiency': 0.95,
            'min_soc': 0.10,
            'max_soc': 0.90,
            'initial_soc': 0.50,
            'degradation_rate_per_cycle': 0.00017,  # 6000 cycle için %80 EOL
            'capex_usd_per_kwh': 350,
            'opex_pct_of_capex': 0.02
        },
        'simulation': {
            'interval_minutes': 15,
            'lookahead_hours': 4,
            'peak_threshold_strategy': 'dynamic',  # 'fixed' veya 'dynamic'
            'peak_threshold_percentile': 85,
            'peak_threshold_fixed_kw': 10000
        },
        'financial': {
            'analysis_years': 10,
            'discount_rate': 0.20,  # WACC %20 (Türkiye)
            'electricity_price_increase_rate': 0.07,  # Yıllık %7 artış
            'currency': 'TRY'
        }
    }
    
    with open('config/config.json', 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    print("✓ config.json oluşturuldu")

def create_requirements_file():
    """Requirements.txt oluştur"""
    
    requirements = """# EMS Peak Shaving - Gerekli Paketler
pandas>=2.0.0
numpy>=1.24.0
matplotlib>=3.7.0
plotly>=5.14.0
scikit-learn>=1.3.0
scipy>=1.11.0
streamlit>=1.28.0
pymodbus>=3.5.0
paho-mqtt>=1.6.1

# Opsiyonel (ML için)
xgboost>=2.0.0
prophet>=1.1.0
"""
    
    with open('requirements.txt', 'w') as f:
        f.write(requirements)
    print("✓ requirements.txt oluşturuldu")

def main():
    """Ana fonksiyon"""
    
    print("🚀 EMS Peak Shaving Projesi Başlatılıyor...\n")
    
    # 1. Klasör yapısı
    print("1️⃣ Proje yapısı oluşturuluyor...")
    create_project_structure()
    
    # 2. Sentetik veri üret
    print("\n2️⃣ Sentetik çimento fabrikası verisi üretiliyor...")
    print("   (Bu 1-2 dakika sürebilir - 1 yıllık 15-dakikalık veri)")
    
    electricity_df = generate_cement_factory_data(
        start_date='2023-01-01',
        end_date='2024-01-01',
        interval_minutes=15
    )
    print(f"   ✓ {len(electricity_df):,} satır elektrik verisi üretildi")
    
    # 3. Üretim verisi
    print("\n3️⃣ Üretim verisi üretiliyor...")
    production_df = generate_production_data(electricity_df)
    print(f"   ✓ {len(production_df)} gün üretim verisi üretildi")
    
    # 4. Tarife yapısı
    print("\n4️⃣ Tarife yapısı oluşturuluyor...")
    tariff = generate_tariff_structure()
    print(f"   ✓ Tarife yapısı hazır")
    
    # 5. Kaydet
    print("\n5️⃣ Veriler kaydediliyor...")
    save_synthetic_data(electricity_df, production_df, tariff)
    
    # 6. Config dosyası
    print("\n6️⃣ Konfigürasyon dosyaları oluşturuluyor...")
    create_config_file()
    create_requirements_file()
    
    # 7. README
    create_readme()
    
    print("\n" + "="*60)
    print("✅ PROJE HAZIR!")
    print("="*60)
    print("\n📂 Oluşturulan dosyalar:")
    print("   data/synthetic/elektrik_tuketim.csv     - Müşteri formatında veri")
    print("   data/synthetic/elektrik_detayli.csv     - Ekipman bazlı veri (internal)")
    print("   data/synthetic/uretim_verisi.csv        - Üretim verileri")
    print("   data/synthetic/tarife_yapisi.json       - Elektrik tarifeleri")
    print("   data/synthetic/veri_ozeti.json          - İstatistikler")
    print("   config/config.json                      - Sistem ayarları")
    print("   requirements.txt                        - Python paketleri")
    print("   README.md                               - Proje dokümantasyonu")
    
    print("\n🚀 Sonraki adımlar:")
    print("   1. pip install -r requirements.txt")
    print("   2. Batarya modelini kodla (models/battery.py)")
    print("   3. Peak shaving algoritmasını kodla (models/controller.py)")
    print("   4. Simülasyonu çalıştır (simulation/simulator.py)")
    
    print("\n💡 Sentetik veriyi incelemek için:")
    print("   python -c \"import pandas as pd; df = pd.read_csv('data/synthetic/elektrik_tuketim.csv'); print(df.head())\"")

def create_readme():
    """README.md oluştur"""
    
    readme = """# EMS Peak Shaving - Enerji Depolama Yönetim Sistemi

Çimento fabrikaları için batarya enerji depolama sistemi (BESS) ile peak shaving optimizasyonu.

## 🎯 Proje Hedefi

Endüstriyel tesislerde elektrik kapasite bedelini (demand charge) azaltarak enerji maliyetlerinde %15-30 tasarruf sağlamak.

## 📁 Proje Yapısı

```
ems-peak-shaving/
├── data/
│   ├── raw/              # Ham müşteri verisi
│   ├── processed/        # İşlenmiş veri
│   └── synthetic/        # Sentetik test verisi
├── models/
│   ├── battery.py        # Batarya modeli
│   ├── controller.py     # Peak shaving algoritması
│   └── forecaster.py     # Load forecasting (ML)
├── simulation/
│   ├── simulator.py      # Ana simülasyon engine
│   └── scenarios.py      # Test senaryoları
├── analysis/
│   ├── metrics.py        # Performans metrikleri
│   ├── financial.py      # ROI hesaplamaları
│   └── visualization.py  # Grafikler
├── config/
│   └── config.json       # Sistem parametreleri
└── outputs/
    ├── reports/          # PDF raporlar
    └── plots/            # Grafikler

```

## 🚀 Kurulum

```bash
# Python sanal ortamı oluştur
python -m venv venv
source venv/bin/activate  # Windows: venv\\Scripts\\activate

# Paketleri yükle
pip install -r requirements.txt

# Sentetik veri üret (ilk kurulumda)
python ems_project_structure.py
```

## 💻 Kullanım

### 1. Veri Hazırlama
```python
import pandas as pd

# Müşteri verisini yükle
df = pd.read_csv('data/raw/musteri_elektrik_verisi.csv')

# Veya sentetik veri kullan
df = pd.read_csv('data/synthetic/elektrik_tuketim.csv')
```

### 2. Simülasyon Çalıştır
```python
from simulation.simulator import PeakShavingSimulator

sim = PeakShavingSimulator(config_path='config/config.json')
results = sim.run(df)

# Sonuçları görselleştir
sim.plot_results(results)
```

### 3. Finansal Analiz
```python
from analysis.financial import calculate_roi

roi_analysis = calculate_roi(
    results=results,
    tariff_structure=tariff,
    battery_capex=350000  # $350k for 1MWh
)

print(f"Yıllık tasarruf: {roi_analysis['annual_saving']:,.0f} TL")
print(f"Geri ödeme: {roi_analysis['payback_years']:.1f} yıl")
```

## 📊 Sentetik Veri Özellikleri

- **Dönem:** 1 yıl (2023-2024)
- **Çözünürlük:** 15 dakika
- **Fabrika tipi:** Çimento fabrikası
- **Ortalama güç:** ~7,500 kW
- **Peak güç:** ~11,000 kW
- **Özellikler:**
  - 24/7 fırın operasyonu
  - Vardiya değişimi spike'ları
  - Hafta sonu düşük kapasite
  - Aylık bakım duruşları
  - Mevsimsel varyasyon

## 🔋 Batarya Sistemi Parametreleri

- **Kapasite:** 1 MWh (yapılandırılabilir)
- **Güç:** 500 kW (0.5C rate)
- **Verimlilik:** %95 (round-trip)
- **SOC limitleri:** %10 - %90
- **Beklenen ömür:** 6,000 cycle / 10 yıl
- **Kimya:** LFP (Lithium Iron Phosphate)

## 📈 Performans Metrikleri

- **Peak reduction:** Peak azaltma oranı (%)
- **Peak shaving effectiveness:** Algoritma başarısı
- **Daily cycles:** Günlük şarj/deşarj döngüsü
- **SOH degradation:** Kapasite kaybı
- **Demand charge savings:** Kapasite bedeli tasarrufu (TL/ay)
- **ROI:** Yatırım geri dönüşü (yıl)

## 🛠️ Geliştirme Yol Haritası

### Faz 1: Temel Sistem ✅
- [x] Proje yapısı
- [x] Sentetik veri üretimi
- [ ] Batarya modeli
- [ ] Basit peak shaving algoritması
- [ ] Temel simülasyon

### Faz 2: Optimizasyon
- [ ] Dynamic threshold optimization
- [ ] ML-based load forecasting
- [ ] Multi-objective optimization
- [ ] Scenario comparison

### Faz 3: Dashboard & Deployment
- [ ] Streamlit dashboard
- [ ] Real-time monitoring
- [ ] API entegrasyonu
- [ ] Cloud deployment

### Faz 4: Production
- [ ] Edge gateway entegrasyonu
- [ ] PCS/Modbus driver
- [ ] MQTT/cloud connectivity
- [ ] Alert & notification sistem

## 📞 İletişim

Proje hakkında sorularınız için: [email]

## 📄 Lisans

Proprietary - Sadece internal kullanım için
"""
    
    with open('README.md', 'w', encoding='utf-8') as f:
        f.write(readme)
    print("✓ README.md oluşturuldu")

if __name__ == "__main__":
    main()
