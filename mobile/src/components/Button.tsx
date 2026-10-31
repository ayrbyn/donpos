import { ActivityIndicator, Pressable, Text } from "react-native";

type Props = {
  title: string;
  onPress: () => void;
  loading?: boolean;
  disabled?: boolean;
  variant?: "primary" | "outline" | "danger";
};

export function Button({
  title,
  onPress,
  loading = false,
  disabled = false,
  variant = "primary",
}: Props) {
  const inactive = disabled || loading;
  const base = "min-h-12 items-center justify-center rounded-lg px-5 py-3";
  const color = {
    primary: "bg-blue-600",
    outline: "border border-slate-300 bg-white",
    danger: "bg-red-600",
  }[variant];
  const textColor = variant === "outline" ? "text-slate-800" : "text-white";

  return (
    <Pressable
      onPress={onPress}
      disabled={inactive}
      className={base + " " + color + (inactive ? " opacity-50" : "")}
    >
      {loading ? (
        <ActivityIndicator color={variant === "outline" ? "#1e293b" : "#ffffff"} />
      ) : (
        <Text className={"text-base font-semibold " + textColor}>{title}</Text>
      )}
    </Pressable>
  );
}