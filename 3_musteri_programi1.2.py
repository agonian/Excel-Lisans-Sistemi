
import subprocess
from cryptography.fernet import Fernet
import pandas as pd
import io
import requests
import zlib
import sys
import os
import time
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QTableWidget, QTableWidgetItem,
                             QLineEdit, QScrollArea, QFrame, QPushButton, QLabel)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QFont

# ================= AYARLAR =================
GIZLI_ANAHTAR = b'='
GITHUB_API_URL = "https://api.github.com/repos/agonian/Excel-Lisans-Sistemi/contents/lisanslar.json"
GITHUB_VERI_RAW_URL = "https://raw.githubusercontent.com/agonian/Excel-Lisans-Sistemi/refs/heads/main/veri.dat" 
GITHUB_VERSIYON_URL = "https://raw.githubusercontent.com/agonian/Excel-Lisans-Sistemi/refs/heads/main/versiyon.json"
MEVCUT_VERSIYON = "1.2" 
# ===========================================

GIZLI_KLASOR = os.path.join(os.environ.get("APPDATA"), "CanliVeriMatrisi")
if not os.path.exists(GIZLI_KLASOR):
    os.makedirs(GIZLI_KLASOR)
VERI_DOSYASI = os.path.join(GIZLI_KLASOR, "veri.dat")

def hwid_getir():
    try:
        cpu_komut = "wmic cpu get processorid"
        cpu_id = subprocess.check_output(cpu_komut, shell=True).decode().strip().split('\n')[1].strip()
        board_komut = "wmic baseboard get serialnumber"
        board_id = subprocess.check_output(board_komut, shell=True).decode().strip().split('\n')[1].strip()
        return f"HWID-{cpu_id}-{board_id}"
    except Exception:
        return "HWID_ALINAMADI"

def veriyi_ramde_ac(dosya_yolu):
    fernet = Fernet(GIZLI_ANAHTAR)
    with open(dosya_yolu, 'rb') as dosya:
        sifreli_veri = dosya.read()
    cozulmus_sikistirilmis_veri = fernet.decrypt(sifreli_veri)
    orijinal_csv_veri = zlib.decompress(cozulmus_sikistirilmis_veri)
    return pd.read_csv(io.BytesIO(orijinal_csv_veri), dtype=str, low_memory=False)

def lisans_kontrol_et(musteri_hwid):
    try:
        headers = {"Accept": "application/vnd.github.v3.raw"}
        cevap = requests.get(GITHUB_API_URL, headers=headers) 
        if cevap.status_code == 200:
            lisanslar = cevap.json()
            for musteri_adi, bilgiler in lisanslar.items():
                if bilgiler.get("hwid") == musteri_hwid and bilgiler.get("durum") == "aktif":
                    return True, musteri_adi
        return False, musteri_hwid
    except:
        return False, musteri_hwid

class ArkaPlanIslemcisi(QThread):
    mesaj_sinyali = pyqtSignal(str)
    hata_sinyali = pyqtSignal(str)
    veri_sinyali = pyqtSignal(object, str)

    def __init__(self, zorunlu_indir=False):
        super().__init__()
        self.zorunlu_indir = zorunlu_indir

    def run(self):
        try:
            self.mesaj_sinyali.emit("Sürüm kontrolü yapılıyor...")
            try:
                # Cache atlatıcı eklendi
                versiyon_url = f"{GITHUB_VERSIYON_URL}?t={time.time()}"
                versiyon_cevap = requests.get(versiyon_url, timeout=10)
                
                if versiyon_cevap.status_code == 200:
                    sunucu_bilgi = versiyon_cevap.json()
                    sunucu_versiyon = sunucu_bilgi.get("versiyon", "1.0")
                    exe_linki = sunucu_bilgi.get("exe_url", "")
                    
                    if float(sunucu_versiyon) > float(MEVCUT_VERSIYON):
                        self.mesaj_sinyali.emit(f"Yeni versiyon (v{sunucu_versiyon}) bulundu! İndiriliyor...\nLütfen programı kapatmayın.")
                        mevcut_exe = sys.executable
                        if getattr(sys, 'frozen', False):
                            eski_exe = mevcut_exe + ".eski"
                            if os.path.exists(eski_exe):
                                os.remove(eski_exe)
                            
                            os.rename(mevcut_exe, eski_exe)
                            yeni_exe_cevap = requests.get(exe_linki, timeout=60)
                            
                            with open(mevcut_exe, "wb") as f:
                                f.write(yeni_exe_cevap.content)
                                
                            subprocess.Popen(mevcut_exe)
                            os._exit(0) # FİŞİ KESİNLİKLE ÇEKEN KOMUT
            except Exception as e:
                # Sessiz hata yerine ekrana basıyoruz
                self.mesaj_sinyali.emit(f"⚠️ Güncelleme Atlandı: {str(e)}")
                time.sleep(3)
            
            self.mesaj_sinyali.emit("Güvenlik protokolleri ve lisans doğrulanıyor...")
            benim_hwid = hwid_getir()
            onay, musteri = lisans_kontrol_et(benim_hwid)
            
            if not onay:
                self.hata_sinyali.emit(f"HWID_ERR:{musteri}")
                return

            if self.zorunlu_indir or not os.path.exists(VERI_DOSYASI):
                self.mesaj_sinyali.emit("Güncel veri matrisi buluttan indiriliyor...\n(Lütfen bekleyin)")
                cevap = requests.get(GITHUB_VERI_RAW_URL, timeout=30)
                if cevap.status_code == 200:
                    with open(VERI_DOSYASI, "wb") as f:
                        f.write(cevap.content)
                else:
                    self.hata_sinyali.emit("Bağlantı Hatası!\nLütfen internet bağlantınızı kontrol edin.")
                    return

            self.mesaj_sinyali.emit("Veri matrisi RAM'e alınıyor ve çözümleniyor...")
            df = veriyi_ramde_ac(VERI_DOSYASI)
            self.veri_sinyali.emit(df, musteri)

        except Exception:
            self.hata_sinyali.emit("Kritik Sistem Hatası:\nAnahtar uyumsuz veya dosya bozuk.")

class AcilisEkrani(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setFixedSize(480, 260)
        self.setStyleSheet("background-color: #2b2b2b; color: white; border: 2px solid #2980b9; border-radius: 8px;")
        
        layout = QVBoxLayout()
        self.lbl_baslik = QLabel(f"📊 CANLI VERİ MATRİSİ  <span style='color:#7f8c8d; font-size:12px;'>v{MEVCUT_VERSIYON}</span>")
        self.lbl_baslik.setAlignment(Qt.AlignCenter)
        self.lbl_baslik.setFont(QFont("Arial", 16, QFont.Bold))
        self.lbl_baslik.setStyleSheet("border: none; color: #3498db; margin-top: 15px;")
        
        self.lbl_durum = QLabel("Sistem başlatılıyor...")
        self.lbl_durum.setAlignment(Qt.AlignCenter)
        self.lbl_durum.setFont(QFont("Arial", 10))
        self.lbl_durum.setStyleSheet("border: none; margin: 10px 0px;")
        
        self.buton_paneli = QWidget()
        self.buton_paneli.setStyleSheet("border: none;")
        buton_layout = QHBoxLayout(self.buton_paneli)
        buton_layout.setContentsMargins(10, 0, 10, 0)

        self.btn_kopyala = QPushButton("📋 HWID Kopyala")
        self.btn_kopyala.setFixedSize(135, 35)
        self.btn_kopyala.setFont(QFont("Arial", 9, QFont.Bold))
        self.btn_kopyala.setStyleSheet("background-color: #f39c12; color: white; border-radius: 4px;")
        self.btn_kopyala.clicked.connect(self.hwid_kopyala)
        
        self.btn_yeniden = QPushButton("🔄 Yeniden Dene")
        self.btn_yeniden.setFixedSize(135, 35)
        self.btn_yeniden.setFont(QFont("Arial", 9, QFont.Bold))
        self.btn_yeniden.setStyleSheet("background-color: #2980b9; color: white; border-radius: 4px;")
        self.btn_yeniden.clicked.connect(self.islemi_baslat)

        self.btn_cikis = QPushButton("❌ Çıkış")
        self.btn_cikis.setFixedSize(135, 35)
        self.btn_cikis.setFont(QFont("Arial", 9, QFont.Bold))
        self.btn_cikis.setStyleSheet("background-color: #c0392b; color: white; border-radius: 4px;")
        self.btn_cikis.clicked.connect(sys.exit)

        buton_layout.addWidget(self.btn_kopyala)
        buton_layout.addWidget(self.btn_yeniden)
        buton_layout.addWidget(self.btn_cikis)

        self.buton_paneli.hide() 
        self.hatali_hwid = ""
        
        layout.addWidget(self.lbl_baslik)
        layout.addWidget(self.lbl_durum)
        layout.addWidget(self.buton_paneli)
        layout.addStretch()
        
        merkez = QWidget()
        merkez.setLayout(layout)
        self.setCentralWidget(merkez)
        
        self.islemi_baslat()

    def islemi_baslat(self):
        self.buton_paneli.hide()
        self.btn_kopyala.hide()
        self.lbl_durum.setText("Bağlantı kuruluyor...")
        self.lbl_durum.setStyleSheet("border: none; margin: 10px 0px;")
        self.btn_kopyala.setText("📋 HWID Kopyala")
        self.btn_kopyala.setStyleSheet("background-color: #f39c12; color: white; border-radius: 4px;")

        self.thread = ArkaPlanIslemcisi(zorunlu_indir=False)
        self.thread.mesaj_sinyali.connect(self.mesaj_guncelle)
        self.thread.hata_sinyali.connect(self.hata_goster)
        self.thread.veri_sinyali.connect(self.basarili_gecis)
        self.thread.start()

    def mesaj_guncelle(self, mesaj):
        self.lbl_durum.setText(mesaj)

    def hata_goster(self, mesaj):
        self.buton_paneli.show()
        if mesaj.startswith("HWID_ERR:"):
            self.hatali_hwid = mesaj.split(":")[1]
            self.lbl_durum.setText(f"❌ Lisans Bulunamadı!\n\nLütfen yetkiliye şu kodu iletin:\n{self.hatali_hwid}")
            self.lbl_durum.setStyleSheet("border: none; color: #e74c3c; font-weight: bold;")
            self.btn_kopyala.show()
        else:
            self.lbl_durum.setText(f"❌ {mesaj}")
            self.lbl_durum.setStyleSheet("border: none; color: #e74c3c; font-weight: bold;")
            self.btn_kopyala.hide() 

    def hwid_kopyala(self):
        panoya_kopyala = QApplication.clipboard()
        panoya_kopyala.setText(self.hatali_hwid)
        self.btn_kopyala.setText("✅ Kopyalandı!")
        self.btn_kopyala.setStyleSheet("background-color: #27ae60; color: white; border-radius: 4px;")

    def basarili_gecis(self, df, musteri):
        self.ana_pencere = ExcelArayuz(df, musteri)
        self.ana_pencere.show()
        self.close()

class ExcelArayuz(QMainWindow):
    def __init__(self, df, musteri_adi):
        super().__init__()
        self.df = df
        self.df.columns = self.df.columns.astype(str)
        self.base_widths = [] 

        self.setWindowTitle(f"Canlı Veri Matrisi v{MEVCUT_VERSIYON} - Lisans: {musteri_adi}")
        self.setStyleSheet("background-color: #2b2b2b; color: white;")
        self.setMinimumSize(1470, 800)
        
        genel_font = QFont("Arial", 9)
        self.setFont(genel_font)

        merkez_widget = QWidget()
        self.setCentralWidget(merkez_widget)
        ana_layout = QVBoxLayout(merkez_widget)
        ana_layout.setContentsMargins(10, 10, 10, 10) 
        ana_layout.setSpacing(5) 

        ust_menu = QWidget()
        ust_menu_layout = QHBoxLayout(ust_menu)
        ust_menu_layout.setContentsMargins(0, 0, 0, 0)
        
        self.btn_guncelle = QPushButton("🔄 Excel'i Güncelle (Sunucudan Çek)")
        self.btn_guncelle.setFixedHeight(35)
        self.btn_guncelle.setFont(QFont("Arial", 10, QFont.Bold))
        self.btn_guncelle_stil = """
            QPushButton { background-color: #27ae60; color: white; padding: 0 15px; border-radius: 4px; } 
            QPushButton:hover { background-color: #2ecc71; }
            QPushButton:disabled { background-color: #7f8c8d; }
        """
        self.btn_guncelle.setStyleSheet(self.btn_guncelle_stil)
        self.btn_guncelle.clicked.connect(self.veriyi_indir_ve_guncelle)

        self.btn_temizle = QPushButton("🧹 Filtreleri Temizle")
        self.btn_temizle.setFixedHeight(35)
        self.btn_temizle.setFont(QFont("Arial", 10, QFont.Bold))
        self.btn_temizle.setStyleSheet("""
            QPushButton { background-color: #c0392b; color: white; padding: 0 15px; border-radius: 4px; } 
            QPushButton:hover { background-color: #e74c3c; }
        """)
        self.btn_temizle.clicked.connect(self.filtreleri_temizle)

        ust_menu_layout.addWidget(self.btn_guncelle)
        ust_menu_layout.addStretch() 
        ust_menu_layout.addWidget(self.btn_temizle)
        ana_layout.addWidget(ust_menu)

        self.arama_scroll = QScrollArea()
        self.arama_scroll.setFixedHeight(55) 
        self.arama_scroll.setWidgetResizable(False) 
        self.arama_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.arama_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn) 
        self.arama_scroll.setFrameShape(QFrame.NoFrame)
        self.arama_scroll.setStyleSheet("QScrollArea { background-color: #2b2b2b; } QScrollBar:vertical { width: 15px; background: transparent; }")

        self.arama_ic_widget = QWidget()
        self.arama_layout = QHBoxLayout(self.arama_ic_widget)
        self.arama_layout.setContentsMargins(0, 0, 0, 0)
        self.arama_layout.setSpacing(0)

        self.arama_kutulari = {}

        self.tablo = QTableWidget()
        self.tablo.setColumnCount(len(self.df.columns))
        self.tablo.setHorizontalHeaderLabels(self.df.columns)
        self.tablo.verticalHeader().setVisible(False)
        self.tablo.setFrameShape(QFrame.NoFrame)
        self.tablo.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        
        self.tablo.setStyleSheet("""
            QTableWidget { background-color: #2b2b2b; color: white; gridline-color: #565b5e; }
            QHeaderView::section { background-color: #3e4142; color: white; border: 1px solid #565b5e; font-weight: bold; padding: 4px; }
            QScrollBar:vertical { width: 15px; }
        """)

        for i, sutun in enumerate(self.df.columns):
            kutu = QLineEdit()
            kutu.setPlaceholderText(f"🔍 {sutun}")
            kutu.setFixedHeight(35) 
            kutu.setStyleSheet("QLineEdit { background-color: #343638; border: 1px solid #565b5e; color: white; padding: 2px 5px; font-size: 14px; }")
            kutu.textChanged.connect(self.filtrele)
            self.arama_kutulari[sutun] = kutu
            self.arama_layout.addWidget(kutu)

        self.arama_scroll.setWidget(self.arama_ic_widget)
        ana_layout.addWidget(self.arama_scroll)
        ana_layout.addWidget(self.tablo)

        self.tabloyu_doldur(self.df)
        self.tablo.resizeColumnsToContents()
        self.base_widths = [self.tablo.columnWidth(i) for i in range(self.tablo.columnCount())]
        self.tablo.horizontalHeader().setStretchLastSection(False)

        self.tablo.horizontalScrollBar().valueChanged.connect(self.arama_scroll.horizontalScrollBar().setValue)
        self.tablo.horizontalHeader().sectionResized.connect(self.sutun_boyut_guncelle)
        self.showMaximized()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'resize_timer'):
            self.resize_timer.stop()
        else:
            self.resize_timer = QTimer()
            self.resize_timer.setSingleShot(True)
            self.resize_timer.timeout.connect(self.responsive_sutun_ayarla)
        self.resize_timer.start(100)

    def responsive_sutun_ayarla(self):
        if not self.base_widths: return
        mevcut_ekran = self.tablo.viewport().width()
        toplam_base = sum(self.base_widths)
        if mevcut_ekran > toplam_base:
            ek_pay = (mevcut_ekran - toplam_base) / len(self.base_widths)
            for i in range(self.tablo.columnCount()):
                self.tablo.setColumnWidth(i, int(self.base_widths[i] + ek_pay))
        else:
            for i in range(self.tablo.columnCount()):
                self.tablo.setColumnWidth(i, self.base_widths[i])
        self.kutulari_hizala()

    def veriyi_indir_ve_guncelle(self):
        self.btn_guncelle.setEnabled(False)
        self.guncelleme_thread = ArkaPlanIslemcisi(zorunlu_indir=True)
        self.guncelleme_thread.mesaj_sinyali.connect(self.guncelleme_mesaj)
        self.guncelleme_thread.hata_sinyali.connect(self.guncelleme_hata)
        self.guncelleme_thread.veri_sinyali.connect(self.guncelleme_basarili)
        self.guncelleme_thread.start()

    def guncelleme_mesaj(self, mesaj):
        self.btn_guncelle.setText(f"⏳ {mesaj}")
        self.btn_guncelle.setStyleSheet("QPushButton { background-color: #f39c12; color: white; padding: 0 15px; border-radius: 4px; }")

    def guncelleme_hata(self, mesaj):
        self.btn_guncelle.setText("❌ Hata Oluştu!")
        self.btn_guncelle.setStyleSheet("QPushButton { background-color: #c0392b; color: white; padding: 0 15px; border-radius: 4px; }")
        self.btn_guncelle.setEnabled(True)
        QTimer.singleShot(4000, self.buton_sifirla)

    def guncelleme_basarili(self, df, musteri):
        self.df = df
        self.filtreleri_temizle()
        self.btn_guncelle.setText("✅ Başarıyla Güncellendi!")
        self.btn_guncelle.setStyleSheet("QPushButton { background-color: #27ae60; color: white; padding: 0 15px; border-radius: 4px; }")
        self.btn_guncelle.setEnabled(True)
        QTimer.singleShot(4000, self.buton_sifirla)

    def buton_sifirla(self):
        self.btn_guncelle.setText("🔄 Excel'i Güncelle (Sunucudan Çek)")
        self.btn_guncelle.setStyleSheet(self.btn_guncelle_stil)

    def kutulari_hizala(self):
        toplam_genislik = 0
        for i in range(self.tablo.columnCount()):
            w = self.tablo.columnWidth(i)
            kutu = self.arama_layout.itemAt(i).widget()
            if isinstance(kutu, QLineEdit): kutu.setFixedWidth(w)
            toplam_genislik += w
        self.arama_ic_widget.setFixedWidth(toplam_genislik)

    def sutun_boyut_guncelle(self, logicalIndex, oldSize, newSize):
        kutu = self.arama_layout.itemAt(logicalIndex).widget()
        if isinstance(kutu, QLineEdit): kutu.setFixedWidth(newSize)
        self.arama_ic_widget.setFixedWidth(self.tablo.horizontalHeader().length())

    def tabloyu_doldur(self, df):
        self.tablo.setRowCount(0)
        gosterilecek_veri = df.head(1000).values.tolist()
        self.tablo.setRowCount(len(gosterilecek_veri))
        for satir_idx, satir_verisi in enumerate(gosterilecek_veri):
            for sutun_idx, hucre_verisi in enumerate(satir_verisi):
                item = QTableWidgetItem(str(hucre_verisi))
                item.setFlags(item.flags() ^ Qt.ItemIsEditable) 
                self.tablo.setItem(satir_idx, sutun_idx, item)

    def filtreleri_temizle(self):
        for kutu in self.arama_kutulari.values():
            kutu.blockSignals(True)
            kutu.clear()
            kutu.blockSignals(False)
        self.filtrele()

    def filtrele(self):
        temp_df = self.df.copy()
        for sutun, kutu in self.arama_kutulari.items():
            arama_metni = kutu.text().lower()
            if arama_metni:
                temp_df = temp_df[temp_df[sutun].astype(str).str.lower().str.contains(arama_metni, na=False)]
        self.tabloyu_doldur(temp_df)

if __name__ == "__main__":
    if getattr(sys, 'frozen', False):
        eski_dosya = sys.executable + ".eski"
        if os.path.exists(eski_dosya):
            try:
                time.sleep(1) 
                os.remove(eski_dosya)
            except:
                pass

    uygulama = QApplication(sys.argv)
    pencere = AcilisEkrani() 
    pencere.show()
    sys.exit(uygulama.exec_())