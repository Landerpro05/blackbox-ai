const timestamp = new Intl.DateTimeFormat("es-ES", {
  dateStyle: "medium",
  timeStyle: "short",
});
export const formatDate = (value: string) => timestamp.format(new Date(value));
