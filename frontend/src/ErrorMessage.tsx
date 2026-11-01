export function ErrorMessage({ error }: { error: string | null }) {
  if (error === null) {
    return null;
  }
  return <p className="error">{error}</p>;
}
