import React, { createContext, useCallback, useContext, useEffect, useState } from "react";

// ── Supported languages ───────────────────────────────────────────────────────

export type Lang = "English" | "Urdu" | "Arabic" | "French";

const RTL_LANGS: Lang[] = ["Urdu", "Arabic"];

const LANG_CODES: Record<Lang, string> = {
  English: "en",
  Urdu: "ur",
  Arabic: "ar",
  French: "fr",
};

// ── Translation keys ──────────────────────────────────────────────────────────

export type Translations = {
  // Navigation
  "nav.dashboard": string;
  "nav.candidates": string;
  "nav.clients": string;
  "nav.jobs": string;
  "nav.reports": string;
  "nav.settings": string;
  "nav.inbox": string;
  "nav.matching": string;
  "nav.logout": string;
  // Common
  "common.save": string;
  "common.saving": string;
  "common.cancel": string;
  "common.loading": string;
  "common.search": string;
  "common.close": string;
  "common.upload": string;
  "common.uploading": string;
  "common.changeName": string;
  // Dashboard
  "dashboard.title": string;
  "dashboard.overview": string;
  "dashboard.notifications": string;
  "dashboard.totalCandidates": string;
  "dashboard.activeJobs": string;
  "dashboard.newToday": string;
  "dashboard.queued": string;
  "dashboard.processing": string;
  "dashboard.done24h": string;
  "dashboard.liveUpdates": string;
  "dashboard.openInbox": string;
  "dashboard.loadingWidgets": string;
  // Settings page
  "settings.title": string;
  "settings.tab.profile": string;
  "settings.tab.account": string;
  "settings.tab.screening": string;
  "settings.tab.notifications": string;
  "settings.tab.preferences": string;
  "settings.tab.security": string;
  // Profile
  "profile.phoneNumber": string;
  "profile.address": string;
  "profile.email": string;
  "profile.company": string;
  "profile.availableHours": string;
  "profile.noName": string;
  "profile.saved": string;
  "profile.savedLocally": string;
  "profile.picUpdated": string;
  "profile.picLocal": string;
  "profile.deleteAccountTitle": string;
  "profile.deleteAccountHint": string;
  "profile.deleteAccountPasswordLabel": string;
  "profile.deleteAccountPasswordPlaceholder": string;
  "profile.deleteAccountNeedPassword": string;
  "profile.deleteAccountButton": string;
  "profile.deleteAccountBusy": string;
  "profile.deleteAccountConfirm": string;
  "profile.deleteAccountToastTitle": string;
  "profile.deleteAccountToastHint": string;
  "profile.deleteAccountCancelConfirm": string;
  "profile.deleteAccountConfirmButton": string;
  "profile.deleteAccountSuccess": string;
  "profile.deleteAccountFailed": string;
  // Account settings
  "account.general": string;
  "account.defaultDashboard": string;
  "account.candidatesPerPage": string;
  "account.defaultTopMatches": string;
  "account.localization": string;
  "account.dateFormat": string;
  "account.timeZone": string;
  "account.language": string;
  "account.saved": string;
  "account.hint": string;
  // Screening settings
  "screening.thresholds": string;
  "screening.minScore": string;
  "screening.showTopMatches": string;
  "screening.weights": string;
  "screening.skills": string;
  "screening.experience": string;
  "screening.certifications": string;
  "screening.automation": string;
  "screening.autoRank": string;
  "screening.autoReject": string;
  "screening.saved": string;
  // Notification settings
  "notif.hint": string;
  "notif.candidateActivity": string;
  "notif.newApplied": string;
  "notif.shortlisted": string;
  "notif.rejected": string;
  "notif.hired": string;
  "notif.alerts": string;
  "notif.topMatchesFound": string;
  "notif.lowMatch": string;
  "notif.reports": string;
  "notif.weeklySummary": string;
  "notif.monthlyReport": string;
  "notif.saved": string;
  // Preferences settings
  "pref.interface": string;
  "pref.theme": string;
  "pref.fontSize": string;
  "pref.defaults": string;
  "pref.candidateSort": string;
  "pref.clientSort": string;
  "pref.jobSort": string;
  "pref.saved": string;
  // Security settings
  "security.password": string;
  "security.currentPwd": string;
  "security.newPwd": string;
  "security.confirmPwd": string;
  "security.changePwd": string;
  "security.changingPwd": string;
  "security.twoFA": string;
  "security.enable2fa": string;
  "security.sessions": string;
  "security.loggedDevices": string;
  "security.thisDevice": string;
  "security.logoutAll": string;
  "security.saved": string;
  "security.accountEmail": string;
  "security.noSessions": string;
  "security.revoke": string;
  "security.sessionRevoked": string;
  "security.signedOutAll": string;
  // Matching page
  "matching.title": string;
  "matching.selectJob": string;
  "matching.loadingJobs": string;
  "matching.filterBy": string;
  "matching.topMatches": string;
  "matching.sortByRank": string;
  "matching.sortByScore": string;
  "matching.sortByMatch": string;
  "matching.sortByName": string;
  "matching.match": string;
  "matching.matching": string;
  "matching.exportResults": string;
  "matching.selectJobPrompt": string;
  "matching.jobDescription": string;
  "matching.candidates": string;
  "matching.noPool": string;
  "matching.viewResume": string;
  "matching.viewProfile": string;
  "matching.compareTop": string;
  "matching.compareCandidates": string;
  "matching.topInsight": string;
  "matching.columnSbert": string;
  "matching.columnSbertHelp": string;
};

export type TranslationKey = keyof Translations;

// ── Translation dictionaries ──────────────────────────────────────────────────

const ENGLISH: Translations = {
  "nav.dashboard": "Dashboard",
  "nav.candidates": "Candidates",
  "nav.clients": "Clients",
  "nav.jobs": "Jobs",
  "nav.reports": "Reports",
  "nav.settings": "Settings",
  "nav.inbox": "Inbox",
  "nav.matching": "Matching",
  "nav.logout": "Log out",

  "common.save": "Save Changes",
  "common.saving": "Saving…",
  "common.cancel": "Cancel",
  "common.loading": "Loading…",
  "common.search": "Search",
  "common.close": "Close",
  "common.upload": "Upload Profile Picture",
  "common.uploading": "Uploading…",
  "common.changeName": "Change name",

  "dashboard.title": "Build Your Talent Pipeline",
  "dashboard.overview": "Overview",
  "dashboard.notifications": "Notifications",
  "dashboard.totalCandidates": "Total Candidates",
  "dashboard.activeJobs": "Active Jobs",
  "dashboard.newToday": "New Candidates Today",
  "dashboard.queued": "Queued",
  "dashboard.processing": "Processing",
  "dashboard.done24h": "Done (24h)",
  "dashboard.liveUpdates": "Live updates.",
  "dashboard.openInbox": "Open full inbox",
  "dashboard.loadingWidgets": "Loading dashboard widgets…",

  "settings.title": "Manage Your Account and System Preferences",
  "settings.tab.profile": "Profile",
  "settings.tab.account": "Account",
  "settings.tab.screening": "Screening",
  "settings.tab.notifications": "Notifications",
  "settings.tab.preferences": "Preferences",
  "settings.tab.security": "Security",

  "profile.phoneNumber": "Phone Number",
  "profile.address": "Address",
  "profile.email": "Email",
  "profile.company": "Company",
  "profile.availableHours": "Available Hours",
  "profile.noName": "(no name)",
  "profile.saved": "Profile saved",
  "profile.savedLocally": "Profile saved locally",
  "profile.picUpdated": "Profile picture updated",
  "profile.picLocal": "Profile picture saved locally",
  "profile.deleteAccountTitle": "Delete account",
  "profile.deleteAccountHint":
    "Permanently remove this Rezume AI account and sign-in access. Jobs you created stay in the system but are no longer tied to you; if you are a candidate, your pool profile is unlinked from this login. Messages and sessions for this account are removed. This cannot be undone.",
  "profile.deleteAccountPasswordLabel": "Confirm with password",
  "profile.deleteAccountPasswordPlaceholder": "Enter your current password",
  "profile.deleteAccountNeedPassword": "Enter your password to confirm deletion.",
  "profile.deleteAccountButton": "Delete my account permanently",
  "profile.deleteAccountBusy": "Deleting…",
  "profile.deleteAccountConfirm":
    "Delete this account permanently? You will lose access immediately. This cannot be undone.",
  "profile.deleteAccountToastTitle": "Confirm deletion",
  "profile.deleteAccountToastHint":
    "A notice appeared above. Click the red button again to delete, or Cancel to go back.",
  "profile.deleteAccountCancelConfirm": "Cancel",
  "profile.deleteAccountConfirmButton": "Yes — delete my account",
  "profile.deleteAccountSuccess": "Your account has been deleted.",
  "profile.deleteAccountFailed": "Could not delete account.",

  "account.general": "General",
  "account.defaultDashboard": "Default Dashboard",
  "account.candidatesPerPage": "Candidates Per Page",
  "account.defaultTopMatches": "Default Top Matches",
  "account.localization": "Localization",
  "account.dateFormat": "Date Format",
  "account.timeZone": "Time Zone",
  "account.language": "Language",
  "account.saved": "Account settings saved",
  "account.hint": "Changes apply on next page visit",

  "screening.thresholds": "Matching Thresholds",
  "screening.minScore": "Minimum Match Score",
  "screening.showTopMatches": "Show Only Top Matches",
  "screening.weights": "Scoring Weights",
  "screening.skills": "Skills Importance",
  "screening.experience": "Experience Importance",
  "screening.certifications": "Certifications",
  "screening.automation": "Automation",
  "screening.autoRank": "Auto Rank Candidates",
  "screening.autoReject": "Auto Reject Low Matches",
  "screening.saved": "Screening settings saved — reload any open page to apply",

  "notif.hint": "Choose when you want to be notified",
  "notif.candidateActivity": "Candidate Activity",
  "notif.newApplied": "New Candidate Applied",
  "notif.shortlisted": "Candidate Shortlisted",
  "notif.rejected": "Candidate Rejected",
  "notif.hired": "Candidate Hired",
  "notif.alerts": "Alerts",
  "notif.topMatchesFound": "Top Matches Found",
  "notif.lowMatch": "Low Match Warning",
  "notif.reports": "Reports",
  "notif.weeklySummary": "Weekly Summary Email",
  "notif.monthlyReport": "Monthly Hiring Report",
  "notif.saved": "Notification settings saved",

  "pref.interface": "Interface",
  "pref.theme": "Theme",
  "pref.fontSize": "Font Size",
  "pref.defaults": "Defaults",
  "pref.candidateSort": "Default Candidate Sort",
  "pref.clientSort": "Default Client Sort",
  "pref.jobSort": "Default Job Sort",
  "pref.saved": "Preferences saved — theme and font applied",

  "security.password": "Password",
  "security.currentPwd": "Current Password",
  "security.newPwd": "New Password",
  "security.confirmPwd": "Confirm Password",
  "security.changePwd": "Change Password",
  "security.changingPwd": "Changing…",
  "security.twoFA": "Two-Factor Authentication",
  "security.enable2fa": "Enable 2FA",
  "security.sessions": "Sessions",
  "security.loggedDevices": "Logged-in Devices",
  "security.thisDevice": "This device",
  "security.logoutAll": "Log Out of All Devices",
  "security.saved": "Security settings saved",
  "security.accountEmail": "Account email",
  "security.noSessions": "No active sessions found.",
  "security.revoke": "Sign out",
  "security.sessionRevoked": "Session signed out",
  "security.signedOutAll": "Signed out on all devices",

  "matching.title": "Matching",
  "matching.selectJob": "Select job",
  "matching.loadingJobs": "Loading jobs…",
  "matching.filterBy": "Filter By",
  "matching.topMatches": "Top Matches",
  "matching.sortByRank": "Sort by Rank",
  "matching.sortByScore": "Sort by Score",
  "matching.sortByMatch": "Sort by Match",
  "matching.sortByName": "Sort by Name (A–Z)",
  "matching.match": "Match",
  "matching.matching": "Matching…",
  "matching.exportResults": "Export Results",
  "matching.selectJobPrompt": "Select a job to view matches.",
  "matching.jobDescription": "Job Description",
  "matching.candidates": "Candidates",
  "matching.noPool": "No matching candidates for this job in pool.",
  "matching.viewResume": "View resume",
  "matching.viewProfile": "View profile »",
  "matching.compareTop": "Compare top",
  "matching.compareCandidates": "Compare Candidates",
  "matching.topInsight": "Top candidate insight",
  "matching.columnSbert": "SBERT",
  "matching.columnSbertHelp":
    "Semantic similarity (résumé embedding vs job). Match uses the cross-encoder plus skills and experience — so it can stay high even when this number looks low.",
};

const URDU: Translations = {
  "nav.dashboard": "ڈیش بورڈ",
  "nav.candidates": "امیدوار",
  "nav.clients": "کلائنٹس",
  "nav.jobs": "ملازمتیں",
  "nav.reports": "رپورٹس",
  "nav.settings": "ترتیبات",
  "nav.inbox": "ان باکس",
  "nav.matching": "ملاپ",
  "nav.logout": "لاگ آؤٹ",

  "common.save": "تبدیلیاں محفوظ کریں",
  "common.saving": "محفوظ ہو رہا ہے…",
  "common.cancel": "منسوخ",
  "common.loading": "لوڈ ہو رہا ہے…",
  "common.search": "تلاش",
  "common.close": "بند کریں",
  "common.upload": "پروفائل تصویر اپ لوڈ کریں",
  "common.uploading": "اپ لوڈ ہو رہا ہے…",
  "common.changeName": "نام تبدیل کریں",

  "dashboard.title": "اپنی ٹیلنٹ پائپ لائن بنائیں",
  "dashboard.overview": "جائزہ",
  "dashboard.notifications": "اطلاعات",
  "dashboard.totalCandidates": "کل امیدوار",
  "dashboard.activeJobs": "فعال ملازمتیں",
  "dashboard.newToday": "آج کے نئے امیدوار",
  "dashboard.queued": "قطار میں",
  "dashboard.processing": "پروسیسنگ",
  "dashboard.done24h": "مکمل (24 گھنٹے)",
  "dashboard.liveUpdates": "براہ راست اپ ڈیٹس۔",
  "dashboard.openInbox": "پورا ان باکس کھولیں",
  "dashboard.loadingWidgets": "ڈیش بورڈ ویجٹس لوڈ ہو رہے ہیں…",

  "settings.title": "اپنا اکاؤنٹ اور سسٹم ترجیحات منظم کریں",
  "settings.tab.profile": "پروفائل",
  "settings.tab.account": "اکاؤنٹ",
  "settings.tab.screening": "اسکریننگ",
  "settings.tab.notifications": "اطلاعات",
  "settings.tab.preferences": "ترجیحات",
  "settings.tab.security": "سیکیورٹی",

  "profile.phoneNumber": "فون نمبر",
  "profile.address": "پتہ",
  "profile.email": "ای میل",
  "profile.company": "کمپنی",
  "profile.availableHours": "دستیاب اوقات",
  "profile.noName": "(کوئی نام نہیں)",
  "profile.saved": "پروفائل محفوظ ہو گئی",
  "profile.savedLocally": "پروفائل مقامی طور پر محفوظ ہو گئی",
  "profile.picUpdated": "پروفائل تصویر اپ ڈیٹ ہو گئی",
  "profile.picLocal": "پروفائل تصویر مقامی طور پر محفوظ ہو گئی",
  "profile.deleteAccountTitle": "اکاؤنٹ حذف کریں",
  "profile.deleteAccountHint":
    "یہ Rezume AI اکاؤنٹ اور لاگ ان مستقل طور پر ہٹا دیں۔ آپ کی بنائی نوکریاں نظام میں رہتی ہیں مگر آپ سے منسلک نہیں رہتیں؛ امیدوار کے طور پر آپ کا پول پروفائل اس لاگ ان سے الگ ہو جاتا ہے۔ پیغامات اور سیشنز حذف ہو جاتے ہیں۔ واپس نہیں ہو سکتا۔",
  "profile.deleteAccountPasswordLabel": "پاس ورڈ سے تصدیق",
  "profile.deleteAccountPasswordPlaceholder": "موجودہ پاس ورڈ درج کریں",
  "profile.deleteAccountNeedPassword": "تصدیق کے لیے اپنا پاس ورڈ درج کریں۔",
  "profile.deleteAccountButton": "میرا اکاؤنٹ مستقل حذف کریں",
  "profile.deleteAccountBusy": "حذف ہو رہا ہے…",
  "profile.deleteAccountConfirm": "اکاؤنٹ مستقل حذف کریں؟ فوری طور پر رسائی ختم ہو جائے گی۔ واپس نہیں ہو سکتا۔",
  "profile.deleteAccountToastTitle": "حذف کی تصدیق",
  "profile.deleteAccountToastHint": "اوپر ایک نوٹس آیا۔ دوبارہ سرخ بٹن دبائیں یا واپس جانے کے لیے منسوخ کریں۔",
  "profile.deleteAccountCancelConfirm": "منسوخ",
  "profile.deleteAccountConfirmButton": "جی ہاں — اکاؤنٹ حذف کریں",
  "profile.deleteAccountSuccess": "آپ کا اکاؤنٹ حذف ہو گیا۔",
  "profile.deleteAccountFailed": "اکاؤنٹ حذف نہیں ہو سکا۔",

  "account.general": "عمومی",
  "account.defaultDashboard": "ڈیفالٹ ڈیش بورڈ",
  "account.candidatesPerPage": "فی صفحہ امیدوار",
  "account.defaultTopMatches": "ڈیفالٹ ٹاپ میچز",
  "account.localization": "لوکلائزیشن",
  "account.dateFormat": "تاریخ فارمیٹ",
  "account.timeZone": "ٹائم زون",
  "account.language": "زبان",
  "account.saved": "اکاؤنٹ ترتیبات محفوظ ہو گئیں",
  "account.hint": "تبدیلیاں اگلی بار صفحہ کھولنے پر لاگو ہوں گی",

  "screening.thresholds": "ملاپ کی حدیں",
  "screening.minScore": "کم از کم میچ اسکور",
  "screening.showTopMatches": "صرف ٹاپ میچز دکھائیں",
  "screening.weights": "اسکورنگ اہمیت",
  "screening.skills": "مہارتوں کی اہمیت",
  "screening.experience": "تجربے کی اہمیت",
  "screening.certifications": "سرٹیفیکیشنز",
  "screening.automation": "خودکاری",
  "screening.autoRank": "امیدواروں کو خودبخود رینک کریں",
  "screening.autoReject": "کم میچ کو خودبخود مسترد کریں",
  "screening.saved": "اسکریننگ ترتیبات محفوظ ہو گئیں",

  "notif.hint": "منتخب کریں کہ آپ کب اطلاع چاہتے ہیں",
  "notif.candidateActivity": "امیدوار کی سرگرمی",
  "notif.newApplied": "نیا امیدوار درخواست دہندہ",
  "notif.shortlisted": "امیدوار شارٹ لسٹ",
  "notif.rejected": "امیدوار مسترد",
  "notif.hired": "امیدوار بھرتی",
  "notif.alerts": "الرٹس",
  "notif.topMatchesFound": "ٹاپ میچز ملے",
  "notif.lowMatch": "کم میچ کی تنبیہ",
  "notif.reports": "رپورٹس",
  "notif.weeklySummary": "ہفتہ وار خلاصہ ای میل",
  "notif.monthlyReport": "ماہانہ بھرتی رپورٹ",
  "notif.saved": "اطلاع ترتیبات محفوظ ہو گئیں",

  "pref.interface": "انٹرفیس",
  "pref.theme": "تھیم",
  "pref.fontSize": "فونٹ سائز",
  "pref.defaults": "ڈیفالٹس",
  "pref.candidateSort": "ڈیفالٹ امیدوار ترتیب",
  "pref.clientSort": "ڈیفالٹ کلائنٹ ترتیب",
  "pref.jobSort": "ڈیفالٹ ملازمت ترتیب",
  "pref.saved": "ترجیحات محفوظ ہو گئیں",

  "security.password": "پاس ورڈ",
  "security.currentPwd": "موجودہ پاس ورڈ",
  "security.newPwd": "نیا پاس ورڈ",
  "security.confirmPwd": "پاس ورڈ کی تصدیق",
  "security.changePwd": "پاس ورڈ تبدیل کریں",
  "security.changingPwd": "تبدیل ہو رہا ہے…",
  "security.twoFA": "دو عنصری تصدیق",
  "security.enable2fa": "2FA فعال کریں",
  "security.sessions": "سیشنز",
  "security.loggedDevices": "لاگ ان آلات",
  "security.thisDevice": "یہ آلہ",
  "security.logoutAll": "تمام آلات سے لاگ آؤٹ کریں",
  "security.saved": "سیکیورٹی ترتیبات محفوظ ہو گئیں",
  "security.accountEmail": "اکاؤنٹ ای میل",
  "security.noSessions": "کوئی فعال سیشن نہیں ملا۔",
  "security.revoke": "لاگ آؤٹ",
  "security.sessionRevoked": "سیشن بند ہو گیا",
  "security.signedOutAll": "تمام آلات پر لاگ آؤٹ",

  "matching.title": "ملاپ",
  "matching.selectJob": "ملازمت منتخب کریں",
  "matching.loadingJobs": "ملازمتیں لوڈ ہو رہی ہیں…",
  "matching.filterBy": "فلٹر بذریعہ",
  "matching.topMatches": "ٹاپ میچز",
  "matching.sortByRank": "رینک کے مطابق ترتیب",
  "matching.sortByScore": "اسکور کے مطابق ترتیب",
  "matching.sortByMatch": "میچ کے مطابق ترتیب",
  "matching.sortByName": "نام کے مطابق ترتیب",
  "matching.match": "ملاپ کریں",
  "matching.matching": "ملاپ ہو رہا ہے…",
  "matching.exportResults": "نتائج برآمد کریں",
  "matching.selectJobPrompt": "میچز دیکھنے کے لیے ملازمت منتخب کریں۔",
  "matching.jobDescription": "ملازمت کی تفصیل",
  "matching.candidates": "امیدوار",
  "matching.noPool": "ابھی تک کوئی امیدوار پول میں نہیں۔",
  "matching.viewResume": "ریزیومے دیکھیں",
  "matching.viewProfile": "پروفائل دیکھیں »",
  "matching.compareTop": "ٹاپ موازنہ کریں",
  "matching.compareCandidates": "امیدواروں کا موازنہ کریں",
  "matching.topInsight": "ٹاپ امیدوار بصیرت",
  "matching.columnSbert": "SBERT",
  "matching.columnSbertHelp":
    "میعاری مشابہت (ریزیومے کا امبیڈنگ ملازمت کے ساتھ)۔ میچ فیصد کراس اینکوڈر اور مہارتوں سے بنتا ہے؛ یہ نمبر کم ہو سکتا ہے جبکہ میٹچ اچھا رہے۔",
};

const ARABIC: Translations = {
  "nav.dashboard": "لوحة التحكم",
  "nav.candidates": "المرشحون",
  "nav.clients": "العملاء",
  "nav.jobs": "الوظائف",
  "nav.reports": "التقارير",
  "nav.settings": "الإعدادات",
  "nav.inbox": "صندوق الوارد",
  "nav.matching": "التوفيق",
  "nav.logout": "تسجيل الخروج",

  "common.save": "حفظ التغييرات",
  "common.saving": "جارٍ الحفظ…",
  "common.cancel": "إلغاء",
  "common.loading": "جارٍ التحميل…",
  "common.search": "بحث",
  "common.close": "إغلاق",
  "common.upload": "رفع صورة الملف الشخصي",
  "common.uploading": "جارٍ الرفع…",
  "common.changeName": "تغيير الاسم",

  "dashboard.title": "ابنِ خط أنابيب المواهب الخاص بك",
  "dashboard.overview": "نظرة عامة",
  "dashboard.notifications": "الإشعارات",
  "dashboard.totalCandidates": "إجمالي المرشحين",
  "dashboard.activeJobs": "الوظائف النشطة",
  "dashboard.newToday": "مرشحون جدد اليوم",
  "dashboard.queued": "قيد الانتظار",
  "dashboard.processing": "قيد المعالجة",
  "dashboard.done24h": "مكتمل (24 ساعة)",
  "dashboard.liveUpdates": "تحديثات مباشرة.",
  "dashboard.openInbox": "فتح صندوق الوارد",
  "dashboard.loadingWidgets": "جارٍ تحميل أدوات لوحة التحكم…",

  "settings.title": "إدارة حسابك وتفضيلات النظام",
  "settings.tab.profile": "الملف الشخصي",
  "settings.tab.account": "الحساب",
  "settings.tab.screening": "الفرز",
  "settings.tab.notifications": "الإشعارات",
  "settings.tab.preferences": "التفضيلات",
  "settings.tab.security": "الأمان",

  "profile.phoneNumber": "رقم الهاتف",
  "profile.address": "العنوان",
  "profile.email": "البريد الإلكتروني",
  "profile.company": "الشركة",
  "profile.availableHours": "ساعات العمل المتاحة",
  "profile.noName": "(لا يوجد اسم)",
  "profile.saved": "تم حفظ الملف الشخصي",
  "profile.savedLocally": "تم حفظ الملف الشخصي محلياً",
  "profile.picUpdated": "تم تحديث صورة الملف الشخصي",
  "profile.picLocal": "تم حفظ صورة الملف الشخصي محلياً",
  "profile.deleteAccountTitle": "حذف الحساب",
  "profile.deleteAccountHint":
    "إزالة حساب Rezume AI وتسجيل الدخول نهائياً. الوظائف التي أنشأتها تبقى في النظام دون ربط بك؛ كمرشح يُفصل ملفك من تسجيل الدخول. تُحذف الرسائل والجلسات. لا يمكن التراجع.",
  "profile.deleteAccountPasswordLabel": "التأكيد بكلمة المرور",
  "profile.deleteAccountPasswordPlaceholder": "أدخل كلمة المرور الحالية",
  "profile.deleteAccountNeedPassword": "أدخل كلمة المرور للتأكيد.",
  "profile.deleteAccountButton": "حذف حسابي نهائياً",
  "profile.deleteAccountBusy": "جارٍ الحذف…",
  "profile.deleteAccountConfirm": "حذف الحساب نهائياً؟ ستفقد الوصول فوراً. لا يمكن التراجع.",
  "profile.deleteAccountToastTitle": "تأكيد الحذف",
  "profile.deleteAccountToastHint": "ظهرت إشعار أعلاه. انقر الزر الأحمر مرة أخرى للحذف، أو إلغاء للتراجع.",
  "profile.deleteAccountCancelConfirm": "إلغاء",
  "profile.deleteAccountConfirmButton": "نعم — احذف حسابي",
  "profile.deleteAccountSuccess": "تم حذف حسابك.",
  "profile.deleteAccountFailed": "تعذر حذف الحساب.",

  "account.general": "عام",
  "account.defaultDashboard": "لوحة التحكم الافتراضية",
  "account.candidatesPerPage": "المرشحون لكل صفحة",
  "account.defaultTopMatches": "أفضل التطابقات الافتراضية",
  "account.localization": "التوطين",
  "account.dateFormat": "تنسيق التاريخ",
  "account.timeZone": "المنطقة الزمنية",
  "account.language": "اللغة",
  "account.saved": "تم حفظ إعدادات الحساب",
  "account.hint": "تُطبَّق التغييرات في الزيارة التالية للصفحة",

  "screening.thresholds": "عتبات التطابق",
  "screening.minScore": "الحد الأدنى لنقاط التطابق",
  "screening.showTopMatches": "عرض أفضل التطابقات فقط",
  "screening.weights": "أوزان التقييم",
  "screening.skills": "أهمية المهارات",
  "screening.experience": "أهمية الخبرة",
  "screening.certifications": "الشهادات",
  "screening.automation": "الأتمتة",
  "screening.autoRank": "ترتيب المرشحين تلقائياً",
  "screening.autoReject": "رفض المطابقات المنخفضة تلقائياً",
  "screening.saved": "تم حفظ إعدادات الفرز",

  "notif.hint": "اختر متى تريد أن تُخطَر",
  "notif.candidateActivity": "نشاط المرشح",
  "notif.newApplied": "مرشح جديد تقدم",
  "notif.shortlisted": "مرشح في القائمة المختصرة",
  "notif.rejected": "مرشح مرفوض",
  "notif.hired": "تم تعيين المرشح",
  "notif.alerts": "التنبيهات",
  "notif.topMatchesFound": "تم العثور على أفضل التطابقات",
  "notif.lowMatch": "تحذير التطابق المنخفض",
  "notif.reports": "التقارير",
  "notif.weeklySummary": "بريد إلكتروني للملخص الأسبوعي",
  "notif.monthlyReport": "تقرير التوظيف الشهري",
  "notif.saved": "تم حفظ إعدادات الإشعارات",

  "pref.interface": "الواجهة",
  "pref.theme": "المظهر",
  "pref.fontSize": "حجم الخط",
  "pref.defaults": "الافتراضيات",
  "pref.candidateSort": "الترتيب الافتراضي للمرشحين",
  "pref.clientSort": "الترتيب الافتراضي للعملاء",
  "pref.jobSort": "الترتيب الافتراضي للوظائف",
  "pref.saved": "تم حفظ التفضيلات",

  "security.password": "كلمة المرور",
  "security.currentPwd": "كلمة المرور الحالية",
  "security.newPwd": "كلمة المرور الجديدة",
  "security.confirmPwd": "تأكيد كلمة المرور",
  "security.changePwd": "تغيير كلمة المرور",
  "security.changingPwd": "جارٍ التغيير…",
  "security.twoFA": "المصادقة الثنائية",
  "security.enable2fa": "تفعيل 2FA",
  "security.sessions": "الجلسات",
  "security.loggedDevices": "الأجهزة المسجلة",
  "security.thisDevice": "هذا الجهاز",
  "security.logoutAll": "تسجيل الخروج من جميع الأجهزة",
  "security.saved": "تم حفظ إعدادات الأمان",
  "security.accountEmail": "البريد الإلكتروني للحساب",
  "security.noSessions": "لم يتم العثور على جلسات نشطة.",
  "security.revoke": "تسجيل الخروج",
  "security.sessionRevoked": "تم إنهاء الجلسة",
  "security.signedOutAll": "تم تسجيل الخروج من جميع الأجهزة",

  "matching.title": "التوفيق",
  "matching.selectJob": "اختر وظيفة",
  "matching.loadingJobs": "جارٍ تحميل الوظائف…",
  "matching.filterBy": "تصفية بواسطة",
  "matching.topMatches": "أفضل التطابقات",
  "matching.sortByRank": "ترتيب حسب الترتيب",
  "matching.sortByScore": "ترتيب حسب النقاط",
  "matching.sortByMatch": "ترتيب حسب التطابق",
  "matching.sortByName": "ترتيب حسب الاسم",
  "matching.match": "توفيق",
  "matching.matching": "جارٍ التوفيق…",
  "matching.exportResults": "تصدير النتائج",
  "matching.selectJobPrompt": "اختر وظيفة لعرض التطابقات.",
  "matching.jobDescription": "وصف الوظيفة",
  "matching.candidates": "المرشحون",
  "matching.noPool": "لا يوجد مرشحون في المجموعة بعد.",
  "matching.viewResume": "عرض السيرة الذاتية",
  "matching.viewProfile": "عرض الملف الشخصي »",
  "matching.compareTop": "مقارنة أفضل",
  "matching.compareCandidates": "مقارنة المرشحين",
  "matching.topInsight": "رؤية المرشح الأول",
  "matching.columnSbert": "SBERT",
  "matching.columnSbertHelp":
    "تشابه دلالي (تضمين السيرة مقابل الوظيفة). نسبة التطابق تعتمد على النموذج الثنائي والمهارات؛ قد يبقى التطابق مرتفعًا رغم انخفاض هذا الرقم.",
};

const FRENCH: Translations = {
  "nav.dashboard": "Tableau de bord",
  "nav.candidates": "Candidats",
  "nav.clients": "Clients",
  "nav.jobs": "Emplois",
  "nav.reports": "Rapports",
  "nav.settings": "Paramètres",
  "nav.inbox": "Boîte de réception",
  "nav.matching": "Correspondance",
  "nav.logout": "Se déconnecter",

  "common.save": "Enregistrer les modifications",
  "common.saving": "Enregistrement…",
  "common.cancel": "Annuler",
  "common.loading": "Chargement…",
  "common.search": "Rechercher",
  "common.close": "Fermer",
  "common.upload": "Télécharger une photo de profil",
  "common.uploading": "Téléchargement…",
  "common.changeName": "Changer le nom",

  "dashboard.title": "Construisez votre pipeline de talents",
  "dashboard.overview": "Aperçu",
  "dashboard.notifications": "Notifications",
  "dashboard.totalCandidates": "Total des candidats",
  "dashboard.activeJobs": "Offres actives",
  "dashboard.newToday": "Nouveaux candidats aujourd'hui",
  "dashboard.queued": "En attente",
  "dashboard.processing": "En cours",
  "dashboard.done24h": "Terminé (24h)",
  "dashboard.liveUpdates": "Mises à jour en direct.",
  "dashboard.openInbox": "Ouvrir la boîte de réception",
  "dashboard.loadingWidgets": "Chargement des widgets…",

  "settings.title": "Gérez votre compte et vos préférences système",
  "settings.tab.profile": "Profil",
  "settings.tab.account": "Compte",
  "settings.tab.screening": "Filtrage",
  "settings.tab.notifications": "Notifications",
  "settings.tab.preferences": "Préférences",
  "settings.tab.security": "Sécurité",

  "profile.phoneNumber": "Numéro de téléphone",
  "profile.address": "Adresse",
  "profile.email": "E-mail",
  "profile.company": "Société",
  "profile.availableHours": "Heures disponibles",
  "profile.noName": "(sans nom)",
  "profile.saved": "Profil enregistré",
  "profile.savedLocally": "Profil enregistré localement",
  "profile.picUpdated": "Photo de profil mise à jour",
  "profile.picLocal": "Photo de profil enregistrée localement",
  "profile.deleteAccountTitle": "Supprimer le compte",
  "profile.deleteAccountHint":
    "Supprime définitivement ce compte Rezume AI et l’accès. Les offres que vous avez créées restent dans le système mais ne vous sont plus liées ; en tant que candidat, votre profil pool est détaché de cette connexion. Messages et sessions sont supprimés. Irréversible.",
  "profile.deleteAccountPasswordLabel": "Confirmer avec le mot de passe",
  "profile.deleteAccountPasswordPlaceholder": "Saisissez votre mot de passe actuel",
  "profile.deleteAccountNeedPassword": "Saisissez votre mot de passe pour confirmer.",
  "profile.deleteAccountButton": "Supprimer définitivement mon compte",
  "profile.deleteAccountBusy": "Suppression…",
  "profile.deleteAccountConfirm":
    "Supprimer ce compte définitivement ? Vous perdrez l’accès immédiatement. Irréversible.",
  "profile.deleteAccountToastTitle": "Confirmer la suppression",
  "profile.deleteAccountToastHint":
    "Un message s’affiche en haut à droite. Cliquez encore sur le bouton rouge pour supprimer, ou Annuler.",
  "profile.deleteAccountCancelConfirm": "Annuler",
  "profile.deleteAccountConfirmButton": "Oui — supprimer mon compte",
  "profile.deleteAccountSuccess": "Votre compte a été supprimé.",
  "profile.deleteAccountFailed": "Impossible de supprimer le compte.",

  "account.general": "Général",
  "account.defaultDashboard": "Tableau de bord par défaut",
  "account.candidatesPerPage": "Candidats par page",
  "account.defaultTopMatches": "Meilleures correspondances par défaut",
  "account.localization": "Localisation",
  "account.dateFormat": "Format de date",
  "account.timeZone": "Fuseau horaire",
  "account.language": "Langue",
  "account.saved": "Paramètres du compte enregistrés",
  "account.hint": "Les modifications s'appliquent à la prochaine visite de la page",

  "screening.thresholds": "Seuils de correspondance",
  "screening.minScore": "Score de correspondance minimum",
  "screening.showTopMatches": "Afficher uniquement les meilleures correspondances",
  "screening.weights": "Poids de notation",
  "screening.skills": "Importance des compétences",
  "screening.experience": "Importance de l'expérience",
  "screening.certifications": "Certifications",
  "screening.automation": "Automatisation",
  "screening.autoRank": "Classer les candidats automatiquement",
  "screening.autoReject": "Rejeter automatiquement les faibles correspondances",
  "screening.saved": "Paramètres de filtrage enregistrés",

  "notif.hint": "Choisissez quand vous souhaitez être notifié",
  "notif.candidateActivity": "Activité des candidats",
  "notif.newApplied": "Nouveau candidat postulé",
  "notif.shortlisted": "Candidat présélectionné",
  "notif.rejected": "Candidat rejeté",
  "notif.hired": "Candidat embauché",
  "notif.alerts": "Alertes",
  "notif.topMatchesFound": "Meilleures correspondances trouvées",
  "notif.lowMatch": "Avertissement de faible correspondance",
  "notif.reports": "Rapports",
  "notif.weeklySummary": "E-mail de résumé hebdomadaire",
  "notif.monthlyReport": "Rapport mensuel de recrutement",
  "notif.saved": "Paramètres de notification enregistrés",

  "pref.interface": "Interface",
  "pref.theme": "Thème",
  "pref.fontSize": "Taille de police",
  "pref.defaults": "Paramètres par défaut",
  "pref.candidateSort": "Tri des candidats par défaut",
  "pref.clientSort": "Tri des clients par défaut",
  "pref.jobSort": "Tri des emplois par défaut",
  "pref.saved": "Préférences enregistrées",

  "security.password": "Mot de passe",
  "security.currentPwd": "Mot de passe actuel",
  "security.newPwd": "Nouveau mot de passe",
  "security.confirmPwd": "Confirmer le mot de passe",
  "security.changePwd": "Changer le mot de passe",
  "security.changingPwd": "Modification…",
  "security.twoFA": "Authentification à deux facteurs",
  "security.enable2fa": "Activer 2FA",
  "security.sessions": "Sessions",
  "security.loggedDevices": "Appareils connectés",
  "security.thisDevice": "Cet appareil",
  "security.logoutAll": "Se déconnecter de tous les appareils",
  "security.saved": "Paramètres de sécurité enregistrés",
  "security.accountEmail": "E-mail du compte",
  "security.noSessions": "Aucune session active trouvée.",
  "security.revoke": "Déconnexion",
  "security.sessionRevoked": "Session terminée",
  "security.signedOutAll": "Déconnexion sur tous les appareils",

  "matching.title": "Correspondance",
  "matching.selectJob": "Sélectionner un emploi",
  "matching.loadingJobs": "Chargement des emplois…",
  "matching.filterBy": "Filtrer par",
  "matching.topMatches": "Meilleures correspondances",
  "matching.sortByRank": "Trier par rang",
  "matching.sortByScore": "Trier par score",
  "matching.sortByMatch": "Trier par correspondance",
  "matching.sortByName": "Trier par nom (A–Z)",
  "matching.match": "Correspondre",
  "matching.matching": "Correspondance en cours…",
  "matching.exportResults": "Exporter les résultats",
  "matching.selectJobPrompt": "Sélectionnez un emploi pour voir les correspondances.",
  "matching.jobDescription": "Description de l'emploi",
  "matching.candidates": "Candidats",
  "matching.noPool": "Aucun candidat dans le pool pour l'instant.",
  "matching.viewResume": "Voir le CV",
  "matching.viewProfile": "Voir le profil »",
  "matching.compareTop": "Comparer le top",
  "matching.compareCandidates": "Comparer les candidats",
  "matching.topInsight": "Aperçu du meilleur candidat",
  "matching.columnSbert": "SBERT",
  "matching.columnSbertHelp":
    "Similarité sémantique (embedding CV vs offre). Le % Match combine le cross-encodeur et l’expérience — il peut rester élevé même si ce nombre est bas.",
};

const TRANSLATIONS: Record<Lang, Translations> = {
  English: ENGLISH,
  Urdu: URDU,
  Arabic: ARABIC,
  French: FRENCH,
};

// ── Helpers ───────────────────────────────────────────────────────────────────

export function readLanguageFromStorage(): Lang {
  try {
    const raw = localStorage.getItem("rezume.settings.account");
    if (!raw) return "English";
    const parsed = JSON.parse(raw);
    return (parsed.language as Lang) || "English";
  } catch {
    return "English";
  }
}

export function applyDocumentLanguage(lang: Lang): void {
  const isRTL = RTL_LANGS.includes(lang);
  document.documentElement.dir = isRTL ? "rtl" : "ltr";
  document.documentElement.lang = LANG_CODES[lang] ?? "en";
}

// ── Context ───────────────────────────────────────────────────────────────────

type LangCtx = {
  language: Lang;
  t: (key: TranslationKey) => string;
  isRTL: boolean;
};

const LanguageContext = createContext<LangCtx>({
  language: "English",
  t: (k) => k,
  isRTL: false,
});

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguage] = useState<Lang>(() => {
    const lang = readLanguageFromStorage();
    applyDocumentLanguage(lang);
    return lang;
  });

  const handleChange = useCallback(() => {
    const lang = readLanguageFromStorage();
    applyDocumentLanguage(lang);
    setLanguage(lang);
  }, []);

  useEffect(() => {
    window.addEventListener("rezume:language-changed", handleChange);
    return () => window.removeEventListener("rezume:language-changed", handleChange);
  }, [handleChange]);

  const t = useCallback(
    (key: TranslationKey): string => {
      const dict = TRANSLATIONS[language];
      return dict[key] ?? TRANSLATIONS.English[key] ?? key;
    },
    [language],
  );

  const isRTL = RTL_LANGS.includes(language);

  return <LanguageContext.Provider value={{ language, t, isRTL }}>{children}</LanguageContext.Provider>;
}

export function useT(): (key: TranslationKey) => string {
  return useContext(LanguageContext).t;
}

export function useIsRTL(): boolean {
  return useContext(LanguageContext).isRTL;
}

export function useLanguage(): Lang {
  return useContext(LanguageContext).language;
}
