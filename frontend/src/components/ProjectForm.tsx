import { useId, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { LoaderCircle, Save, ShieldCheck } from "lucide-react";
import { ApiError } from "../services/api";
import type { ProjectInput } from "../types/api";

export function ProjectForm({
  initial = { name: "", description: "", base_url: "" },
  onSave,
  cancelTo,
  editing = false,
}: {
  initial?: ProjectInput;
  onSave: (data: ProjectInput) => Promise<void>;
  cancelTo: string;
  editing?: boolean;
}) {
  const id = useId();
  const [data, setData] = useState<ProjectInput>(initial);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [fields, setFields] = useState<Record<string, string>>({});
  const change = (field: keyof ProjectInput, value: string) => {
    setData((current) => ({ ...current, [field]: value }));
    setFields((current) => ({ ...current, [field]: "" }));
  };
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (saving) return;
    const clean = {
      name: data.name.trim(),
      description: data.description.trim(),
      base_url: data.base_url.trim(),
    };
    if (!clean.name) {
      setFields({ name: "Escribe un nombre para el proyecto." });
      return;
    }
    setSaving(true);
    setError("");
    setFields({});
    try {
      await onSave(clean);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "No se pudo guardar el proyecto.",
      );
      if (caught instanceof ApiError) setFields(caught.fields);
    } finally {
      setSaving(false);
    }
  };
  return (
    <form className="panel project-form" onSubmit={submit} aria-busy={saving}>
      <div className="panel-heading">
        <div>
          <h2>
            {editing ? "Datos del proyecto" : "Un nuevo espacio de testing"}
          </h2>
          <p>Los campos con * son obligatorios.</p>
        </div>
      </div>
      <fieldset disabled={saving} className="project-form-fields">
        <div className="form-field">
          <label htmlFor={`${id}-name`}>
            Nombre del proyecto <span>*</span>
          </label>
          <input
            id={`${id}-name`}
            name="name"
            required
            maxLength={120}
            autoFocus
            value={data.name}
            onChange={(event) => change("name", event.target.value)}
            placeholder="Mi aplicación web"
            aria-invalid={!!fields.name}
            aria-describedby={fields.name ? `${id}-name-error` : undefined}
          />
          {fields.name && (
            <p className="field-error" id={`${id}-name-error`}>
              {fields.name}
            </p>
          )}
        </div>
        <div className="form-field">
          <label htmlFor={`${id}-url`}>
            URL base <span>*</span>
          </label>
          <input
            id={`${id}-url`}
            name="base_url"
            type="url"
            inputMode="url"
            required
            maxLength={2048}
            value={data.base_url}
            onChange={(event) => change("base_url", event.target.value)}
            placeholder="https://mi-aplicacion.com"
            aria-invalid={!!fields.base_url}
            aria-describedby={`${id}-url-hint ${fields.base_url ? `${id}-url-error` : ""}`}
          />
          <p id={`${id}-url-hint`}>
            HTTP o HTTPS. Sin credenciales, parámetros de consulta ni
            fragmentos.
          </p>
          {fields.base_url && (
            <p className="field-error" id={`${id}-url-error`}>
              {fields.base_url}
            </p>
          )}
        </div>
        <div className="form-field">
          <label htmlFor={`${id}-description`}>
            Descripción <span className="optional-field">Opcional</span>
          </label>
          <textarea
            id={`${id}-description`}
            name="description"
            maxLength={4000}
            rows={5}
            value={data.description}
            onChange={(event) => change("description", event.target.value)}
            placeholder="Qué hace tu aplicación y qué te gustaría probar."
            aria-invalid={!!fields.description}
            aria-describedby={
              fields.description ? `${id}-description-error` : undefined
            }
          />
          <div className="field-counter">{data.description.length} / 4000</div>
          {fields.description && (
            <p className="field-error" id={`${id}-description-error`}>
              {fields.description}
            </p>
          )}
        </div>
      </fieldset>
      <div className="form-safety">
        <ShieldCheck size={18} />
        <p>
          Guardar este proyecto no visitará su URL ni iniciará ningún análisis.
          La autorización para testing se configurará junto al motor.
        </p>
      </div>
      {error && (
        <div className="inline-alert error-alert" role="alert">
          {error}
        </div>
      )}
      <div className="form-actions">
        {!saving && (
          <Link className="button-secondary" to={cancelTo}>
            Cancelar
          </Link>
        )}
        <button className="button-primary" type="submit" disabled={saving}>
          {saving ? (
            <LoaderCircle size={15} className="spinning" />
          ) : (
            <Save size={15} />
          )}
          {saving
            ? "Guardando…"
            : editing
              ? "Guardar cambios"
              : "Crear proyecto"}
        </button>
      </div>
    </form>
  );
}
