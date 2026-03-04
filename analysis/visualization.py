"""
Visualization - Simülasyon Sonuçlarını Görselleştir
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path

# Türkçe karakterler için
plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


def plot_load_profile_comparison(results_df, output_path='outputs/plots'):
    """Orijinal vs azaltılmış yük profili"""
    
    fig, axes = plt.subplots(2, 1, figsize=(14, 8))
    
    # İlk 7 gün göster (daha okunaklı)
    df_week = results_df.head(7 * 24 * 4)  # 7 gün x 24 saat x 4 (15-dakikalık)
    
    # Üst grafik: Load comparison
    ax1 = axes[0]
    ax1.plot(df_week['timestamp'], df_week['original_load_kw'], 
             label='Orijinal Yük', color='red', alpha=0.7, linewidth=1.5)
    ax1.plot(df_week['timestamp'], df_week['net_load_kw'], 
             label='BESS ile Azaltılmış Yük', color='blue', alpha=0.8, linewidth=1.5)
    ax1.axhline(y=df_week['original_load_kw'].max(), color='red', 
                linestyle='--', alpha=0.5, label='Orijinal Peak')
    ax1.axhline(y=df_week['net_load_kw'].max(), color='blue', 
                linestyle='--', alpha=0.5, label='Azaltılmış Peak')
    
    ax1.set_ylabel('Güç (kW)', fontsize=11)
    ax1.set_title('Elektrik Tüketim Profili - İlk 7 Gün', fontsize=13, fontweight='bold')
    ax1.legend(loc='upper right')
    ax1.grid(True, alpha=0.3)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%d-%m'))
    
    # Alt grafik: Battery power
    ax2 = axes[1]
    colors = df_week['battery_power_kw'].apply(
        lambda x: 'green' if x < 0 else 'orange' if x > 0 else 'gray'
    )
    ax2.bar(df_week['timestamp'], df_week['battery_power_kw'], 
            color=colors, alpha=0.6, width=0.01)
    ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    
    ax2.set_xlabel('Tarih', fontsize=11)
    ax2.set_ylabel('Batarya Gücü (kW)', fontsize=11)
    ax2.set_title('Batarya İşlemleri (Pozitif=Deşarj, Negatif=Şarj)', 
                  fontsize=13, fontweight='bold')
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%d-%m'))
    
    plt.tight_layout()
    
    # Kaydet
    output = Path(output_path)
    output.mkdir(parents=True, exist_ok=True)
    plt.savefig(output / 'load_profile_comparison.png', dpi=150, bbox_inches='tight')
    print(f"✅ Grafik kaydedildi: {output}/load_profile_comparison.png")
    
    plt.close()


def plot_soc_over_time(results_df, output_path='outputs/plots'):
    """SOC zamanla değişimi"""
    
    fig, ax = plt.subplots(figsize=(14, 5))
    
    # İlk 30 gün
    df_month = results_df.head(30 * 24 * 4)
    
    ax.plot(df_month['timestamp'], df_month['battery_soc'] * 100, 
            color='purple', linewidth=1.5)
    ax.axhline(y=90, color='red', linestyle='--', alpha=0.5, label='Max SOC (90%)')
    ax.axhline(y=10, color='orange', linestyle='--', alpha=0.5, label='Min SOC (10%)')
    ax.fill_between(df_month['timestamp'], 10, 90, alpha=0.1, color='green')
    
    ax.set_xlabel('Tarih', fontsize=11)
    ax.set_ylabel('SOC (%)', fontsize=11)
    ax.set_title('Batarya SOC (State of Charge) - İlk 30 Gün', 
                 fontsize=13, fontweight='bold')
    ax.legend(loc='upper right')
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d-%m'))
    ax.set_ylim(0, 100)
    
    plt.tight_layout()
    
    # Kaydet
    output = Path(output_path)
    output.mkdir(parents=True, exist_ok=True)
    plt.savefig(output / 'soc_over_time.png', dpi=150, bbox_inches='tight')
    print(f"✅ Grafik kaydedildi: {output}/soc_over_time.png")
    
    plt.close()


def plot_peak_reduction_summary(results_df, output_path='outputs/plots'):
    """Peak reduction özet grafik"""
    
    original_peak = results_df['original_load_kw'].max()
    reduced_peak = results_df['net_load_kw'].max()
    
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    
    # Sol: Bar chart
    ax1 = axes[0]
    bars = ax1.bar(['Orijinal Peak', 'BESS ile Peak'], 
                   [original_peak, reduced_peak],
                   color=['red', 'blue'], alpha=0.7)
    
    # Değerleri göster
    for bar in bars:
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:,.0f} kW',
                ha='center', va='bottom', fontsize=11, fontweight='bold')
    
    reduction = original_peak - reduced_peak
    reduction_pct = (reduction / original_peak) * 100
    ax1.text(0.5, original_peak * 0.5, 
            f'Azaltım:\n{reduction:.0f} kW\n({reduction_pct:.1f}%)',
            ha='center', va='center', fontsize=12, fontweight='bold',
            bbox=dict(boxstyle='round', facecolor='yellow', alpha=0.5))
    
    ax1.set_ylabel('Peak Güç (kW)', fontsize=11)
    ax1.set_title('Peak Demand Karşılaştırması', fontsize=13, fontweight='bold')
    ax1.grid(True, alpha=0.3, axis='y')
    
    # Sağ: Histogram
    ax2 = axes[1]
    ax2.hist(results_df['original_load_kw'], bins=50, alpha=0.5, 
            label='Orijinal', color='red', edgecolor='black')
    ax2.hist(results_df['net_load_kw'], bins=50, alpha=0.5, 
            label='BESS ile', color='blue', edgecolor='black')
    ax2.axvline(x=original_peak, color='red', linestyle='--', linewidth=2)
    ax2.axvline(x=reduced_peak, color='blue', linestyle='--', linewidth=2)
    
    ax2.set_xlabel('Güç (kW)', fontsize=11)
    ax2.set_ylabel('Frekans', fontsize=11)
    ax2.set_title('Yük Dağılımı', fontsize=13, fontweight='bold')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # Kaydet
    output = Path(output_path)
    output.mkdir(parents=True, exist_ok=True)
    plt.savefig(output / 'peak_reduction_summary.png', dpi=150, bbox_inches='tight')
    print(f"✅ Grafik kaydedildi: {output}/peak_reduction_summary.png")
    
    plt.close()


def main():
    """Ana fonksiyon"""
    
    print("\n📊 Simülasyon Sonuçları Görselleştiriliyor...")
    print("=" * 60)
    
    # Sonuçları yükle
    results_df = pd.read_csv('outputs/simulation_results.csv')
    results_df['timestamp'] = pd.to_datetime(results_df['timestamp'])
    
    print(f"\n✅ {len(results_df):,} satır veri yüklendi")
    print(f"   Dönem: {results_df['timestamp'].min()} - {results_df['timestamp'].max()}")
    
    # Grafikler oluştur
    print("\n📈 Grafikler oluşturuluyor...")
    
    plot_load_profile_comparison(results_df)
    plot_soc_over_time(results_df)
    plot_peak_reduction_summary(results_df)
    
    print("\n" + "=" * 60)
    print("✅ TÜM GRAFİKLER OLUŞTURULDU!")
    print("=" * 60)
    print("\n📂 Grafik dosyaları:")
    print("   outputs/plots/load_profile_comparison.png")
    print("   outputs/plots/soc_over_time.png")
    print("   outputs/plots/peak_reduction_summary.png")


if __name__ == "__main__":
    main()
