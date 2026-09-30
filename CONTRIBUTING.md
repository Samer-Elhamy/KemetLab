# 🤝 دليل المساهمة والتطوير في منظومة KemetLab

أهلاً بك في فريق تطوير مشروع تخرج **KemetLab**! 🎓
هذا الدليل يوضح قواعد العمل الجماعي لضمان بقاء الكود نظيفاً وسهل الصيانة.

---

## 📋 القواعد الأساسية (Core Guidelines)

1. **العمل عبر الفروع (Branching Strategy):**
   - لا تقم بالرفع المباشر على فرع `main` أبداً.
   - لكل ميزة أو مهمة، أنشئ فرعاً جديداً باسم معبر:
     ```bash
     git checkout -b feature/your-feature-name
     # أو
     git checkout -b fix/issue-name
     ```

2. **التكامل والاختبار قبل الـ Push:**
   - تأكد من تشغيل الاختبارات السريعة قبل إرسال التعديلات:
     ```powershell
     python -m unittest tests/test_local_runtime.py
     ```

3. **الحفاظ على سرية البيانات (No Secrets in Git):**
   - ممنوع تماماً رفع أي ملفات `.env` أو مفاتيح API أو كلمات سر.
   - ملف `.gitignore` محمي ومضبوط لتجاهل كافة الملفات الحساسة وقواعد بيانات التجارب (`graph.db`).

4. **رسائل الـ Commit:**
   - اكتب رسائل الـ commit بأسلوب واضح وموجز، مثلاً:
     - `feat: add hybrid fallback for gemini models`
     - `fix: resolve cycle counter stagnation check`
     - `docs: update setup instructions for windows`

5. **فتح Pull Request (PR):**
   - بعد الانتهاء من التعديلات واختبارها، ارفع فرعك إلى GitHub وافتح PR للمراجعة والمناقشة مع البشمهندس سامر وباقي التيم.

---
شكراً لمساهمتكم في نجاح مشروع تخرجنا معاً! 🚀
