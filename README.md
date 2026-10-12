NIKO TELEKOM — YENİLƏMƏ SERVERİNİ QURMA PAKETİ
================================================

Bu paket GitHub Actions vasitəsilə Windows EXE yığmaq, GitHub Release-də
yerləşdirmək və latest.json yeniləmə manifestini GitHub Pages-də dərc etmək
üçün hazırlanıb.

VACİB: Mən sənin GitHub hesabına daxil ola bilmədiyim üçün serveri sənin
adından internetdə dərc edə bilmərəm. Bu paket serveri qurmağa hazırdır;
GitHub hesabında bir dəfə quraşdırma addımlarını etməlisən.

1) GitHub-da yeni REPOSITORY yarat
- GitHub-a daxil ol.
- New repository seç.
- Ad ver: niko-telekom-updates
- Public seç (GitHub Free-də Pages üçün ən rahat variant).
- README əlavə etməmək olar.

2) Bu qovluqdakı bütün faylları repository-yə yüklə
Ən asan yol: GitHub repository səhifəsində Add file -> Upload files.
Gizli .github qovluğunun və içindəki workflows/release-and-update.yml
faylının da yükləndiyinə diqqət et. GitHub web upload-da gizli qovluq çətinlik
yaratsa, GitHub Desktop ilə repository-ni clone edib bütün faylları kopyala,
commit və push et.

3) GitHub Pages-i aktivləşdir
Repository -> Settings -> Pages
Build and deployment -> Source: GitHub Actions seç.
GitHub sənədləri: https://docs.github.com/en/pages

4) İlk versiyanı yarat
Repository -> Releases -> Create a new release:
- Tag: v30.0.0
- Publish release.
Bu tag workflow-u işə salacaq. Actions bölməsində workflow-nun uğurla
bitməsini gözlə. Workflow Windows EXE-ni build edir, release asset kimi
yükləyir və latest.json-u Pages-də dərc edir.

5) Proqramın içində manifest ünvanını daxil et
GitHub username və repo adı ilə ünvan bu formada olacaq:
https://YOUR-USERNAME.github.io/niko-telekom-updates/latest.json

YOUR-USERNAME yerinə GitHub username-ni yaz.
NIKO TELEKOM proqramında “Proqram yeniləməsi” bölməsini aç:
- Manifest HTTPS ünvanını daxil et
- “Ünvanı yadda saxla”
- “Yeniləməni yoxla”

6) Gələcək versiya necə buraxılır
Mənbə kodunu yenilə və VERSION='30.0.0' sətrinin əsas versiya dəyərini
saxla. Sonra GitHub-da yeni release tag yarat, məsələn v30.0.1 və ya v31.0.0.
Workflow həmin tag-a uyğun versiya ilə EXE hazırlayacaq və latest.json-u
yeniləyəcək.

NƏTİCƏ:
- EXE GitHub Releases-də olacaq.
- latest.json GitHub Pages-də olacaq.
- Proqram manifestdən versiyanı yoxlayacaq və SHA-256 uyğunluğunu yoxlayaraq
  yeni EXE-ni Downloads qovluğuna endirəcək.
- Proqram endirilən EXE-ni öz-özünə əvəz etmir; proqramı bağlayıb yeni EXE-ni
  əl ilə açmaq lazımdır.
- Məhsullar/satışlar yerli SQLite bazasında qalır.

TƏHLÜKƏSİZLİK VƏ MƏHDUDİYYƏTLƏR:
- GitHub Pages public olacaq; manifestdə məxfi məlumat yerləşdirmə.
- SHA-256 endirmə zamanı faylın eyni olduğunu yoxlayır, müəllifin kimliyini
  kriptoqrafik sertifikatla təsdiqləmir.
- Bu qurulum üçün GitHub hesabı və bir dəfə əl ilə repository/Pages setup lazımdır.
- Bu paketdə hazır EXE yoxdur. EXE GitHub Actions-da Windows runner vasitəsilə
  yığılacaq.
- Workflow-nun real GitHub hesabında işləməsi burada canlı olaraq test edilməyib.
