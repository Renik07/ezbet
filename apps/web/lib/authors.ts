import { formatCategoryLabel } from "@/lib/category";

const CATEGORY_AUTHORS: Record<string, string> = {
  "Футбол": "Олег И.",
  "Баскетбол": "Даниил К.",
  "Хоккей": "Сергей М.",
  "Теннис": "Алина Р.",
  "MMA": "Роман В.",
  "ММА": "Роман В.",
  "Бокс": "Роман В.",
  "Киберспорт": "Дмитрий Н.",
  "Автоспорт": "Антон Д.",
  "Олимпиада": "Мария С.",
  "Другие виды": "Илья П.",
  "Здоровье": "Елена К.",
  "Деньги": "Михаил О.",
  "Технологии": "Кирилл А.",
  "Беттинг": "Михаил О."
};

export function getArticleAuthor(category?: string) {
  const label = formatCategoryLabel(category);
  return CATEGORY_AUTHORS[label] ?? "Олег И.";
}
