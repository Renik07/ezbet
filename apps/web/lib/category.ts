const CATEGORY_LABELS: Record<string, string> = {
  general: "Общее",
  football: "Футбол",
  hockey: "Хоккей",
  basketball: "Баскетбол",
  tennis: "Теннис",
  mma: "ММА",
  boxing: "Бокс",
  fencing: "Фехтование",
  volleyball: "Волейбол",
  handball: "Гандбол",
  swimming: "Плавание",
  athletics: "Легкая атлетика",
  biathlon: "Биатлон",
  skiing: "Лыжи",
  figure_skating: "Фигурное катание",
  gymnastics: "Гимнастика",
  motorsport: "Автоспорт",
  chess: "Шахматы",
  esports: "Киберспорт",
  betting: "Беттинг"
};

export function formatCategoryLabel(category?: string) {
  if (!category) {
    return "Общее";
  }

  return CATEGORY_LABELS[category] ?? category;
}
