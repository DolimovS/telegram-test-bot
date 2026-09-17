# Cloudflare Workers + D1

**Holat: deployga tayyor, hali ishga tushirilmagan.** Boshlash, sahifalash, arxivlash, arxivdan qaytarish va faqat topshirishsiz testni xavfsiz o‘chirish qoidalari Cloudflare variantiga ko‘chirildi. Unit/integration mantiq testlari o‘tgan. Haqiqiy Cloudflare hisobidagi D1 migration, dry-run/deploy va webhook sinovi keyingi bosqichda bajariladi. Hozirgi faol bot lokal polling bilan ishlaydi.

Bu katalog botning Cloudflare uchun yangi server variantidir. O‘zbek tugmalar, 4 raqamli yangi kodlar, admin himoyasi, faqat shaxsiy chat, bitta xabarda barcha javoblar, tasdiqlash, bitta urinish va natija dizayni saqlanadi. Eski Python varianti lokal ishlash va qaytish uchun loyiha ildizida qoladi.

## Tuzilishi

- `src/worker.js`: maxfiy sarlavha bilan himoyalangan webhook, takroriy update himoyasi, cron va doimiy xabar navbati.
- `src/store.js`: D1, parametrli SQL, atomik topshirish va test yaratish.
- `src/handler.js`: admin/o‘quvchi oqimlari.
- `src/presentation.js`: javoblarni tekshirish va ko‘rinish.
- `migrations/0001_initial.sql`: bo‘sh D1 bazasining sxemasi.

Ichki sanalar UTC Unix soniyalari; ekranda Toshkent vaqti. Har daqiqadagi cron muddatli testlarni yopadi va natija xabarlarini navbatga qo‘yadi. Deadline topshirish SQL so‘rovida ham tekshiriladi: cron kechiksa ham testga yangi javob qabul qilinmaydi. O‘quvchi tarixida natijalar muddat tugashi bilan ochiladi.

## Lokal tekshirish

Node.js 22.13+ (testlar uchun `node:sqlite`) va Python 3.11+ kerak.

```sh
cd cloudflare
npm ci
npm test
npx wrangler d1 migrations apply DB --local
npx wrangler deploy --dry-run
```

`.dev.vars.example` nusxasini `.dev.vars` deb saqlash mumkin. Lokal devda haqiqiy token kerak emas; testlar sun’iy Telegram javoblari bilan ishlaydi. `.dev.vars` Git’dan chiqarilgan. Haqiqiy token bilan dev webhookka tasodifan so‘rov yubormang.

## Birinchi joylashtirish

GitHub push serverni avtomatik ishga tushirmaydi. Cloudflare hisobiga kirish va quyidagi bir martalik sozlash kerak. Workers **Free** rejasida qoling; pullik tarifni tanlash shart emas. Bepul kvotalar cheklangan, cheksiz foydalanish yoki kafolatlangan uzluksizlik va’da qilinmaydi.

```sh
cd cloudflare
npm ci
npx wrangler login
npx wrangler d1 create telegram-test-bot
```

Chiqqan D1 database ID’ni `wrangler.jsonc` ichidagi nol qiymat o‘rniga yozing. Bu ID token emas. `DB` binding nomini o‘zgartirmang.

```sh
npx wrangler d1 migrations apply DB --remote
npx wrangler secret put BOT_TOKEN
npx wrangler secret put ADMIN_ID
npx wrangler secret put WEBHOOK_SECRET
npx wrangler deploy
```

Tokenni faqat maxfiy interaktiv so‘rovga kiriting. Admin uchun haqiqiy raqamli Telegram user ID ishlatiladi. Webhook maxfiy qiymati tasodifiy 32–256 ta lotin harfi, raqam, `_` yoki `-` dan iborat bo‘lsin; uni parol menejerida saqlang. `.env`, `.dev.vars`, token yoki SQL eksportni GitHub’ga qo‘shmang. `/health` faqat konfiguratsiya borligini ko‘rsatadi, token yoki bazadagi ma’lumotni ko‘rsatmaydi.

## Mavjud bazani saqlab ko‘chirish va ishga o‘tkazish

1. Lokal Python botini to‘xtating. Ko‘chirish davomida uni qayta ishga tushirmang: yangi topshirishlar eski bazaga yozilib qolmasin.
2. Lokal SQLite bazasining zaxira nusxasini saqlang. Quyidagi eksport izchil read-only snapshot oladi va manba bazani o‘zgartirmaydi:

```sh
python scripts/export_legacy.py --db ../bot.sqlite3 --out .private/legacy-data.sql
```

3. Faqat yangi, test/topshirishlari **bo‘sh** D1 bazasiga import qiling. Mavjud D1 ma’lumotiga aralashtirmang. SQL faylda javob kalitlari va Telegram ID bor; `.private/` Git’dan chiqarilgan.

```sh
npx wrangler d1 execute DB --remote --file .private/legacy-data.sql
```

4. Eski test kodlari, kalitlar, javoblar, sanalar va ballar saqlanadi. Qisqa muddatli tasdiqlash oynalari va admin drafti ko‘chirilmaydi; tasdiqlanmagan javob qayta yuboriladi. Test va topshirish sonlarini eksportdagi sonlar bilan solishtiring:

```sh
npx wrangler d1 execute DB --remote --command "SELECT COUNT(*) AS tests FROM tests; SELECT COUNT(*) AS attempts FROM attempts;"
```

5. Worker deploy qilingan va sog‘lom bo‘lgach webhookni ulang. Script tokenni lokal `.env`/`.dev.vars` dan o‘qiydi yoki yashirin so‘raydi; maxfiy qiymatni buyruq argumentiga bermang. Worker’da sozlangan aynan o‘sha webhook secret ishlatilishi kerak.

```sh
python scripts/webhook.py --url https://YOUR-WORKER.YOUR-SUBDOMAIN.workers.dev
```

Webhook bitta parallel ulanish bilan sozlanadi; bu admin tugmalari va kalit xabarlari tartibini saqlashga yordam beradi. Lokal polling va webhook bir vaqtda ishlamasin. Telegram’da foydalanuvchi o‘zi sinaydi. Eski lokal bazani o‘chirmang.

## Navbat, cheklovlar va kuzatuv

Webhook qabul qilingach javoblar D1 navbatiga atomik yoziladi. Telegram xatolari va tezlik limiti qayta urinish bilan boshqariladi. Har ishga tushishda 8 tagacha xabar yuboriladi, cron qolganini davom ettiradi. Katta navbat yoki juda uzun natijalarda yetkazish bir necha daqiqa davom etishi mumkin; tarixdan ochilgan natijani ko‘rish mumkin. Bloklangan chatlar va Telegram rad etgan xabarlar `sent=2` bilan belgilanadi. Tarmoq xabarni yetkazganidan keyin uzilsa bildirishnoma takrorlanishi mumkin, ammo test/topshirish takrorlanmaydi.

```sh
npx wrangler d1 execute DB --remote --command "SELECT sent,COUNT(*) FROM outbox GROUP BY sent;"
npx wrangler tail
```

Loglar token, webhook URL’ga qo‘shilgan token yoki foydalanuvchi javoblarini chiqarmaydi. Muntazam D1 eksport/zaxira saqlang. Agar xizmatni lokalga qaytarmoqchi bo‘lsangiz avval webhookni `python scripts/webhook.py --remove` bilan uzing. Cloudflare’da yangi topshirishlar bo‘lgan bo‘lsa **avval D1 ma’lumotlarini lokalga ko‘chirish kerak**; eski lokal bazani shunchaki ishga tushirish yangi natijalarni yo‘qotadi.

Rasmiy manbalar: [Workers narxlari](https://developers.cloudflare.com/workers/platform/pricing/), [D1 narxlari](https://developers.cloudflare.com/d1/platform/pricing/), [D1 batch tranzaksiyalari](https://developers.cloudflare.com/d1/worker-api/d1-database/), [Cron](https://developers.cloudflare.com/workers/configuration/cron-triggers/), [Telegram webhook](https://core.telegram.org/bots/api#setwebhook).
