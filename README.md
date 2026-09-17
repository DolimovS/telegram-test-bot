# Telegram test bot

**Hozirgi ishlaydigan variant — lokal Python bot.** [Cloudflare tayyorlov loyihasi](cloudflare/README.md) alohida katalogda saqlangan; hali deploy yoki bazani ko‘chirish qilinmagan. Yangi arxiv/o‘chirish imkoniyatlari avval lokal botda sinovdan o‘tadi. GitHub push o‘z-o‘zidan Cloudflare deployment qilmaydi.

## Boshlash va test boshqaruvi

`/start` dan keyin pastki klaviaturada **▶️ Boshlash** va **📚 Mening tarixim** tugmalari doimiy ko‘rinadi. Boshlash bosh menyuga qaytaradi va adminning tugallanmagan yangi test holatini bekor qiladi.

Admin **Testlar** bo‘limida beshtadan sahifalangan ro‘yxatni ko‘radi. Har bir testda holati, muddat, natija rejimi va topshirishlar soni bor. **Arxiv** bo‘limi asosiy ro‘yxatdan alohida.

- **Arxivlash** testni yopadi va asosiy ro‘yxatdan olib tashlaydi. Oldingi topshirishlar, ballar va tarix saqlanadi; kechiktirilgan natijalar ochiladi.
- **Arxivdan qaytarish** asosiy ro‘yxatga qaytaradi, lekin test yopiq qoladi. Yangi variant yoki qayta topshirish uchun yangi test yaratiladi.
- **Butunlay o‘chirish** faqat tasdiqlangan topshirishi yo‘q test uchun mavjud. Alohida tasdiqlash tugmasi talab qilinadi; tasdiqlash paytida topshirishlar qayta tekshiriladi. Agar kimdir shu orada topshirgan bo‘lsa, o‘chirish rad etiladi va arxivlash taklif qilinadi.
- O‘chirilgan testning kodi qayta ishlatilmaydi. Eski tasdiqlash tugmalari boshqa testga javob yozolmaydi.

## Cloudflare’ga keyin ko‘chirishga tayyorlik

Hozir hisob ochish yoki hostingga ulanish shart emas; bot lokal ishlaydi. Cloudflare hisobi ochilgach, ish quyidagi tartibda bajariladi:

1. Cloudflare Free hisobiga kirish va D1 bazasini tayyorlash.
2. Repository’dagi Cloudflare variantida **Boshlash, arxiv/o‘chirish, arxiv holati va qayta ishlatilmaydigan kodlar** qoidalari tayyor. Cloudflare hisobida D1 bazasini yaratib, migrationni qo‘llash.
3. Maxfiy token/admin ID/webhook secret sozlash; ularni GitHub yoki chatga qo‘ymaslik.
4. Lokal botni qisqa vaqtga to‘xtatib, izchil SQLite zaxira va eksport olish. Testlar, topshirishlar, arxivlar va band/qayta ishlatilmaydigan kodlar sonini yangi bazada solishtirish.
5. Webhook va avtomatik yopish/natija yuborishni sinovdan o‘tkazish, so‘ng serverni faollashtirish. Lokal polling va server webhook bir vaqtda ishlamaydi.

Cloudflare variantining mantiq, maxfiylik, takroriy webhook, navbat, arxiv/o‘chirish va eksport testlari o‘tgan. Hisobga ulanishdan keyin rasmiy Wrangler build, D1 migration va Telegram webhook sinovi deploydan oldin bajariladi.

Python 3.11+; qo‘shimcha paketlar kerak emas. Interfeys o‘zbek tilida. Faqat shaxsiy chatda ishlaydi.

## Ishga tushirish

1. `.env.example` faylini `.env` deb nusxalang.
2. `.env` ichida `BOT_TOKEN` va yagona administratorning raqamli `ADMIN_ID` qiymatini lokal kiriting. Tokenni chatga yoki GitHub’ga yubormang.
3. Loyiha papkasida `python -m unittest -v` bilan tekshiring.
4. `python bot.py` buyrug‘i bilan ishga tushiring.

Admin panelidagi Test yaratish tugmasi natija rejimini tanlatadi. Kalit va ixtiyoriy muddat bitta xabarda: `ABCD | 2026-12-31 18:00` yoki `ABCD | yo'q`. Sana Asia/Tashkent (UTC+5). /cancel admin yaratish holatini bekor qiladi. Har bir yangi test alohida, bazada qayta ishlatilmaydigan kod oladi. Testlar panelida muddatdan oldin ham yopish mumkin. PDF fayllarni o‘qituvchi o‘zi tarqatadi.

O‘quvchi `4827 ABCD` yoki `4827 1-A, 2-B, 3-C, 4-D` formatida kod va barcha javoblarni bitta xabarda yuboradi. Tasdiqlash 30 daqiqa amal qiladi. Har testga bitta yakuniy topshirish; qayta topshirish va tahrir yo‘q. Natijada ball va xato savollar raqami ko‘rsatiladi, kalit oshkor qilinmaydi. Kechiktirilgan natijalar tarixda ham yopiq qoladi. Bot yopilganda natijalarni xabarda yuborishga urinadi; tarixdan ham ko‘rish mumkin.

## Doimiy ishlash

Kompyuter o‘chiq/uyquda bo‘lsa bot ishlamaydi. Doimiy serverda bitta bot jarayonini systemd yoki boshqa supervisor bilan qayta ishga tushirish sozlamasi orqali yuriting. DB_PATH doimiy diskda bo‘lsin; vaqtinchalik hosting diski ma’lumotni yo‘qotadi. Server UTC soatini sinxron saqlang. SQLite bazasi javob kalitlari va Telegram ID larini saqlaydi: faylga kirishni cheklang va muntazam zaxiralang (ishlayotgan bazani SQLite backup API bilan). Bot offline bo‘lgan vaqtda muddat o‘tgan test qayta ishga tushganda yopiladi; topshirishda muddat har safar tekshiriladi. Xabar yetkazishda tarmoq uzilishi takroriy bildirishnomaga olib kelishi mumkin, lekin topshirish takrorlanmaydi. Pullik hosting yaratilmagan yoki joylashtirilmagan.

`BOT_TOKEN` va `ADMIN_ID` berilmagani sababli Telegram bilan jonli sinov bajarilmagan. Lokal testlar asosiy mantiqni tekshiradi.

Yangi test kodlari 1000–9999 oralig‘idagi 4 raqamdan iborat. Eski kodlar o‘zgarmaydi. Yopilgan test kodlari ham qayta ishlatilmaydi; 9000 ta kod band bo‘lsa yangi test yaratish aniq xabar bilan to‘xtaydi.
