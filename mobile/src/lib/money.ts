export function formatRupiah(value: number): string {
  const sign = value < 0 ? "-" : "";
  const digits = Math.abs(Math.trunc(value)).toString();
  const withDots = digits.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return sign + "Rp " + withDots;
}

export function parseRupiah(text: string): number {
  const digits = text.replace(/\D/g, "").slice(0, 12);
  return digits ? Number(digits) : 0;
}