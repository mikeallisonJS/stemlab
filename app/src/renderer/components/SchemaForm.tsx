import { resolveSchema } from "../recipe";
import type { JsonSchema } from "../types";

interface Props {
  /** An object schema; one field is rendered per property */
  schema: JsonSchema;
  /** The document the schema's $refs point into */
  root?: JsonSchema;
  value: Record<string, unknown>;
  onChange: (value: Record<string, unknown>) => void;
  /** What an unset field resolves to, shown as the placeholder */
  resolved?: Record<string, unknown>;
}

function display(value: unknown): string {
  if (value === undefined || value === null) return "";
  return Array.isArray(value) ? value.join(", ") : String(value);
}

/**
 * A form generated from JSON Schema. Fields left empty are omitted from the
 * value, so defaults keep coming from the engine instead of being frozen
 * into the recipe.
 */
export function SchemaForm({ schema, root, value, onChange, resolved }: Props) {
  const properties = schema.properties ?? {};
  const set = (name: string, next: unknown) => {
    const copy = { ...value };
    if (next === undefined || next === "") delete copy[name];
    else copy[name] = next;
    onChange(copy);
  };

  return (
    <div className="form">
      {Object.entries(properties).map(([name, raw]) => {
        const field = resolveSchema(raw, root ?? schema);
        const current = value[name];
        const fallback = resolved?.[name] ?? field.default;
        const hint = fallback === undefined || fallback === null ? "" : display(fallback);
        const id = `field-${name}`;
        let control;

        if (field.enum) {
          control = (
            <select id={id} value={current === undefined ? "" : String(current)} onChange={(e) => {
              const picked = field.enum?.find((option) => String(option) === e.target.value);
              set(name, e.target.value === "" ? undefined : picked);
            }}>
              <option value="">{hint ? `default (${hint})` : "default"}</option>
              {field.enum.map((option) => (
                <option key={String(option)} value={String(option)}>{String(option)}</option>
              ))}
            </select>
          );
        } else if (field.type === "boolean") {
          control = (
            <select id={id} value={current === undefined ? "" : String(current)}
              onChange={(e) => set(name, e.target.value === "" ? undefined : e.target.value === "true")}>
              <option value="">{hint ? `default (${hint})` : "default"}</option>
              <option value="true">true</option>
              <option value="false">false</option>
            </select>
          );
        } else if (field.type === "integer" || field.type === "number") {
          control = (
            <input id={id} type="number" value={current === undefined ? "" : String(current)} placeholder={hint}
              min={field.minimum} max={field.maximum} step={field.type === "integer" ? 1 : "any"}
              onChange={(e) => {
                if (e.target.value === "") return set(name, undefined);
                const parsed = Number(e.target.value);
                if (!Number.isNaN(parsed)) set(name, field.type === "integer" ? Math.round(parsed) : parsed);
              }} />
          );
        } else if (field.type === "array") {
          // Lists of numbers (ensemble weights) are typed comma separated
          control = (
            <input id={id} type="text" defaultValue={display(current)} placeholder={hint || "comma separated"}
              key={display(current)}
              onBlur={(e) => {
                const parts = e.target.value.split(",").map((part) => part.trim()).filter(Boolean);
                if (!parts.length) return set(name, undefined);
                const numbers = parts.map(Number);
                set(name, numbers.every((n) => !Number.isNaN(n)) ? numbers : parts);
              }} />
          );
        } else {
          control = (
            <input id={id} type="text" value={current === undefined ? "" : String(current)} placeholder={hint}
              onChange={(e) => set(name, e.target.value)} />
          );
        }

        return (
          <label key={name} className="field" htmlFor={id} title={field.description}>
            <span className="field-name">{name}</span>
            {control}
            {field.description && <span className="field-help">{field.description}</span>}
          </label>
        );
      })}
    </div>
  );
}
