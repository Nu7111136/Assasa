# Rakhza tester guide / رکھزا ٹیسٹر گائیڈ

## English
1. Open the HTTPS link NZ sends you (staging is https://staging.rakhza.digital).
   Internet is required.
2. Optional install: **Android Chrome:** menu (?) > Add to Home screen / Install
   app. **iPhone Safari:** Share > Add to Home Screen > Add. If the install option
   is absent, use the browser link normally.
3. Sign up with your own phone number (`03XXXXXXXXX`), a test name, a business
   type, and a new test-only 6-digit MPIN. Never reuse your JazzCash/bank MPIN.
   Phone is not verified in this POC.
4. Switch **EN / اردو** and check layout. NZ must allowlist your phone number before
   tester controls appear. Contact NZ if **Next day / Reset** are missing.
5. Tap **Next day** to add one simulated day each time. Watch **TEST: Day N** and
   days left. After day 5, an unpaid account should go to **Upgrade**. The buttons
   remain on Upgrade: tap **Reset** to return to real time. If the real trial has
   already expired, Reset still leaves you on Upgrade; tell NZ. Simulation is only
   for this browser session and does not affect other testers or real billing.
6. On Upgrade, allowlisted testers can tap **Pay Rs 299 (test)**. That is a virtual
   payment: one calendar month opens and Rs 299 is added to NZ’s **test wallet** on Review
   payments. No real JazzCash. To practise the live form, submit a unique fake TID
   such as `TEST-YOURINITIALS-001` (5-64 letters/digits/hyphens) and leave it pending.
   **Do NOT transfer money. Never share a JazzCash PIN, OTP, or receipt.** Ask NZ
   before approving a live-looking TID: approval grants one calendar month and Reset does not undo it.
7. Log out and log back in. On login, **Forgot MPIN?** needs the signup phone
   Rakhza office. Report issues to NZ: phone/browser model, EN/Urdu,
   steps, expected vs actual result, and a screenshot without phone/CNIC/MPIN/TID.


## اردو
1. NZ کا بھیجا ہوا HTTPS لنک کھولیں (staging: https://staging.rakhza.digital)۔
   انٹرنیٹ ضروری ہے۔
2. فون پر شامل کرنا اختیاری ہے: **Android Chrome:** مینو (⋮) > Add to Home screen
   یا Install app۔ **iPhone Safari:** Share > Add to Home Screen > Add۔ یہ آپشن
   نہ ملے تو براؤزر میں لنک استعمال کریں۔
3. اپنے فون نمبر (`03XXXXXXXXX`)، فرضی نام اور پتے، فرضی 13 ہندسوں کے شناختی نمبر
   مثلاً `12345-1234567-1`، اور صرف ٹیسٹ کے لیے نئے چھ ہندسوں کے ایم پن سے
   سائن اپ کریں۔ ای میل خالی چھوڑ سکتے ہیں۔ اصل شناختی نمبر یا JazzCash/بینک کا
   ایم پن نہ دیں۔ اس نمونے میں فون یا شناختی نمبر کی تصدیق نہیں ہوتی۔
4. **EN / اردو** بدل کر ترتیب دیکھیں۔ NZ پہلے آپ کا فون نمبر ٹیسٹر فہرست میں شامل
   کرے گا۔ **اگلا دن / اصل تاریخ** کے بٹن نہ ہوں تو NZ کو بتائیں۔
5. **اگلا دن (Next day)** ہر بار ایک آزمائشی دن بڑھاتا ہے۔ **آزمائش: دن N** اور باقی
   دن دیکھیں۔ پانچویں دن کے بعد بغیر ادائیگی والا اکاؤنٹ Upgrade پر جانا چاہیے۔
   وہاں بھی بٹن ہوں گے؛ **اصل تاریخ (Reset)** سے حقیقی تاریخ واپس آتی ہے۔ اگر اصل
   آزمائشی مدت بھی ختم ہو چکی ہو تو Upgrade ہی کھلے گا؛ NZ کو بتائیں۔ یہ تبدیلی
   صرف اسی براؤزر کے سیشن کے لیے ہے، دوسرے ٹیسٹر یا اصل بلنگ نہیں بدلتے۔
6. Upgrade پر ٹیسٹر **299 روپے ادا کریں (ٹیسٹ)** دبا سکتے ہیں۔ یہ مجازی ادائیگی ہے:
   30 دن کھل جاتے ہیں اور NZ کے ٹیسٹ والیٹ میں 299 روپے لگتے ہیں۔ اصل JazzCash نہیں۔
   لائیو فارم کی مشق کے لیے منفرد فرضی TID مثلاً `TEST-AB-001` جمع کریں۔ **اصل رقم
   نہ بھیجیں۔ JazzCash PIN یا OTP نہ دیں۔** حقیقی نما TID منظور کرنے سے پہلے NZ سے پوچھیں۔
7. لاگ آؤٹ اور دوبارہ لاگ اِن بھی آزمائیں۔ ایم پن بھول جائیں تو لاگ ان پر **ایم پن
   بھول گئے؟** دبائیں؛ رجسٹریشن والا فون اور وہی شناختی نمبر درکار ہے۔ مسئلہ NZ کو بتائیں: فون اور براؤزر، زبان،
   کیے گئے مراحل، متوقع اور اصل نتیجہ۔ تصویر میں فون، شناختی نمبر، ایم پن یا TID
   نہ دکھائیں۔
