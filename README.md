# ⚗️ KemetLab: Self-Organizing Multi-Agent Architecture for Long-Running Scientific Experimentation

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Architecture: MAS-FSM](https://img.shields.io/badge/Architecture-Decentralized%20FSM-emerald.svg)]()

> **مشروع تخرج KemetLab للأنظمة الذكية ذاتية التنظيم**
> معمارية وكلاء ذكاء اصطناعي لامركزية قادرة على إدارة التجارب العلمية المعقدة وطويلة الأمد، تكوين فرق بحث ذاتية، النقد والتحكيم العلمي، وتخزين المعرفة والمسارات المسدودة (Dead-End Memory).

---

## 🌟 دليل البدء السريع لزملائي في الفريق (Team Welcome & Quickstart)
أهلاً بكم يا شباب! المستودع ده تم تجهيزه عشان يشتغل عند أي حد فيكم بسهولة شديدة، وبأقل خطوات ممكنة سواء كان عندكم كارت شاشة خارجي أو شغالين بـ API Cloud.

### 🚀 التثبيت والتشغيل في خطوة واحدة (One-Click Setup)

#### لمستخدمي Windows (PowerShell):
افتح التيرمينال داخل المجلد وشغل السكريبت:
```powershell
.\setup.ps1
```

#### لمستخدمي Windows (CMD / Batch):
```cmd
setup.bat
```

هذا السكريبت يقوم تلقائياً بـ:
1. إنشاء البيئة الافتراضية `.venv` وتفعيلها.
2. ترقية `pip` وتثبيت كافة المكتبات المطلوبة من `requirements.txt`.
3. فحص سلامة النظام وتأكيد نجاح التثبيت.

---

## 🧠 دورة حياة المنظومة (How It Works)

المنظومة تعمل عبر آلة حالة منتهية لامركزية (**FSM**):
1. **طرح الفرضيات (`PROPOSE`):** وكلاء البحث يقترحون فرضيات وأكواد جديدة استناداً لهدف التجربة.
2. **المناظرة والنقد العلمي (`REVIEW`):** وكلاء التحكيم ينقدون الفكرة ويصوتون عليها قبل حرق أي حوسبة.
3. **التنفيذ المعزول (`RUN_TEAM`):** تشغيل الكود في بيئة معزولة وقياس النتائج بدقة.
4. **الترقية والذاكرة (`CHECK_RESULTS`):**
   - ترقية التجربة كـ **Champion** إذا حققت نتيجة أفضل.
   - حفظ الفشل في سجل المسارات المسدودة (**Dead-End Memory** في `graph.db`) لتفادي تكرار الخطأ.
5. **كاشف الركود (`STAGNATION`):** عند توقف التحسن، يتفكك الفريق تلقائياً ويعاد تشكيل جولة جديدة.

---

## 🛠️ كيفية تشغيل تجربة (Running Experiments)

### 1. تجربة سريعة للتأكد من سلامة النظام (Smoke Test):
```powershell
.\.venv\Scripts\Activate.ps1
python launch.py my_run --task task-smoke-local --run --cycles 3
```

### 2. تشغيل لوحة التحكم والمراقبة التفاعلية (Streamlit Dashboard):
```powershell
streamlit run local/dashboard/app.py
```
ثم افتح المتصفح على: `http://localhost:8501`

---

## 📁 هيكل المشروع (Project Structure)

```text
KemetLab/
├── launch.py                  # نقطة الانطلاق الرئيسية لتشغيل المهام
├── setup.ps1 / setup.bat      # سكريبت الإعداد السريع بضغطة زر
├── requirements.txt           # المكتبات والاعتماديات البرمجية
├── local/
│   ├── orchestrator/          # المحرك التنفيذي وإدارة آلة الحالة (FSM & Team Runner)
│   ├── memory/                # قاعدة المعرفة والرسم البياني (Graph-RAG & graph.db)
│   ├── llm/                   # بوابة توجيه النماذج (Gemini, Claude, OpenRouter)
│   ├── dashboard/             # لوحة المتابعة التفاعلية والشات الذكي (Streamlit)
│   ├── prompts/               # نصوص التوجيه الذكية للوكلاء (Meta & Worker prompts)
│   └── schemas/               # مخططات التحقق من صحة JSON (Schemas)
├── task-smoke-local/          # بيئة تجارب سريعة خفيفة للاختبار
└── docs/                      # التوثيق المعماري وتفاصيل التشغيل
```

---

## 🤝 المساهمة والتطوير (Contributing)
يرجى قراءة [CONTRIBUTING.md](CONTRIBUTING.md) للتعرف على طريقة تنظيم الفروع (Branches) وإرسال التعديلات (Pull Requests).
