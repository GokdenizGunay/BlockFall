# BlockFall

Blok yerleştirme oyunu. Parçaları 8×8 tahtaya yerleştir, dolan satır ve sütunları temizle, kombolarla puanını katla. İnternet bağlantısı gerektirmez.

<img src="docs/ekran-goruntusu.png" alt="BlockFall ekran görüntüsü" width="320">

## Özellikler

- Sürükle-bırak ile parça yerleştirme, yerleşecek yerin ve temizlenecek satırların önizlemesi
- Kombo, çoklu satır ve tahtayı tamamen temizleme bonusları
- Yerleştirme, temizleme, parçacık ve yazı animasyonları
- En iyi skor kaydı

**Kısayollar:** F2 / Ctrl+N yeni oyun · Ctrl+Q çıkış · F11 tam ekran (Windows)

## Sürümler

Depo iki ayrı projeden oluşur:

| Klasör | Platform | Çıktı |
|---|---|---|
| [`debian/`](debian) | Pardus ve Debian tabanlı sistemler | `.deb` paketi |
| [`windows/`](windows) | Windows 10 / 11 | Tek dosya `BlockFall.exe` |

Hazır dosyalar [Releases](https://github.com/GokdenizGunay/BlockFall/releases) sayfasındadır.

## Pardus / Debian

`.deb` dosyasına çift tıkla veya:

```bash
sudo apt install ./blockfall_<sürüm>_all.deb
```

Gerekenler (Pardus'ta hazır gelir): `python3`, `python3-gi`, `python3-gi-cairo`, `python3-cairo`, `gir1.2-gtk-3.0`. Kurulum menü kaydı, simge ve masaüstü kısayolu ekler. Kaldırmak için: `sudo apt remove blockfall`

**Derleme** (Python 3 yeterli, Windows'ta da çalışır):

```bash
cd debian
python build_deb.py
```

Çıktı: `debian/dist/blockfall_<sürüm>_all.deb` · Doğrudan çalıştırmak için: `python3 debian/src/blockfall.py`

| Yol | İçerik |
|---|---|
| `debian/src/blockfall.py` | Oyun (GTK3 + Cairo) |
| `debian/data/` | Masaüstü dosyası, simge, kurulum betikleri |
| `debian/build_deb.py` | `.deb` paketi üreticisi |

## Windows

`BlockFall.exe` kurulum gerektirmez; indirip çalıştırman yeterli. Font ve tüm bileşenler dosyanın içindedir. En iyi skor `%LOCALAPPDATA%\BlockFall\save.json` dosyasına kaydedilir.

İmzasız olduğu için ilk açılışta Windows SmartScreen uyarı verebilir: **Ek bilgi → Yine de çalıştır**.

**Derleme** (Python 3.11+):

```bash
cd windows
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python build_exe.py
```

Çıktı: `windows/dist/BlockFall.exe` · Doğrudan çalıştırmak için: `.venv\Scripts\python src\blockfall.py`

| Yol | İçerik |
|---|---|
| `windows/src/blockfall.py` | Oyun (pygame-ce + Cairo) |
| `windows/assets/fonts/` | Gömülü Quicksand fontu |
| `windows/build_exe.py` | Simgeyi üretir, PyInstaller ile tek `.exe` derler |
| `windows/requirements.txt` | Derleme için gereken paketler |
