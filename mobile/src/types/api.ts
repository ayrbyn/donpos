export type Product = {
  id: string;
  name: string;
  sku: string | null;
  barcode: string | null;
  price: number;
  stock: number;
  is_active: boolean;
  category_id: string | null;
};