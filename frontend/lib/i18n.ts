export type Lang = "en" | "uk";

const dict = {
  en: {
    heroTitle: "Turn visitors into qualified leads — automatically",
    heroSubtitle:
      "Our AI assistant interviews your prospects 24/7, captures project details, scores every lead and hands your team a ready-to-act summary.",
    heroCta: "Try the AI intake chat",
    feature1Title: "Conversational intake",
    feature1Text: "An adaptive AI chat replaces static forms and follows up on vague answers.",
    feature2Title: "Instant notifications",
    feature2Text: "New qualified leads land in Telegram and email with one-tap actions.",
    feature3Title: "Built-in mini CRM",
    feature3Text: "Transcripts, AI summaries, scoring and analytics in one dashboard.",
    chatTitle: "AI Intake Assistant",
    chatPlaceholder: "Type your answer…",
    chatSend: "Send",
    chatRestart: "Start over",
    chatDone: "Conversation finished. Thank you!",
    chatUpload: "Attach a file",
    chatOpen: "Chat with us",
    adminLink: "Admin dashboard",
  },
  uk: {
    heroTitle: "Перетворюйте відвідувачів на кваліфіковані ліди — автоматично",
    heroSubtitle:
      "Наш AI-асистент опитує потенційних клієнтів 24/7, збирає деталі проєкту, оцінює кожен лід і передає команді готовий підсумок.",
    heroCta: "Спробувати AI-чат",
    feature1Title: "Розмовний прийом заявок",
    feature1Text: "Адаптивний AI-чат замінює статичні форми та уточнює нечіткі відповіді.",
    feature2Title: "Миттєві сповіщення",
    feature2Text: "Нові кваліфіковані ліди надходять у Telegram та email з кнопками дій.",
    feature3Title: "Вбудована міні-CRM",
    feature3Text: "Транскрипти, AI-підсумки, скоринг та аналітика в одній панелі.",
    chatTitle: "AI-асистент прийому",
    chatPlaceholder: "Введіть відповідь…",
    chatSend: "Надіслати",
    chatRestart: "Почати заново",
    chatDone: "Розмову завершено. Дякуємо!",
    chatUpload: "Прикріпити файл",
    chatOpen: "Написати нам",
    adminLink: "Панель адміністратора",
  },
} as const;

export type TKey = keyof (typeof dict)["en"];

export function t(lang: Lang, key: TKey): string {
  return dict[lang][key] || dict.en[key];
}
