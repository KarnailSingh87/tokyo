export type RiskTier = 0 | 1 | 2 | 3;

export type ToolCategory =
  | "file"
  | "terminal"
  | "browser"
  | "screen"
  | "voice"
  | "memory"
  | "network"
  | "notify";

export type JsonType = "string" | "number" | "boolean" | "array" | "object";

export interface JsonSchemaField {
  type: JsonType;
  description?: string;
  enum?: (string | number)[];
  items?: JsonSchemaField;
  properties?: Record<string, JsonSchemaField>;
  required?: string[];
}

export interface JsonSchemaObject extends JsonSchemaField {
  type: "object";
  properties: Record<string, JsonSchemaField>;
  required?: string[];
}

export interface ToolDefinition {
  name: string;
  version: string;
  description: string;
  category: ToolCategory;
  riskTier: RiskTier;
  enabled: boolean;
  inputSchema: JsonSchemaObject;
  outputSchema?: JsonSchemaObject;
}

export interface ValidationResult {
  ok: boolean;
  errors: string[];
}

function validateField(field: JsonSchemaField, value: unknown, path: string, errors: string[]): void {
  if (field.enum && !(field.enum as unknown[]).includes(value)) {
    errors.push(`${path}: must be one of ${field.enum.join(", ")}`);
    return;
  }
  switch (field.type) {
    case "string":
      if (typeof value !== "string") errors.push(`${path}: expected string`);
      break;
    case "number":
      if (typeof value !== "number" || Number.isNaN(value)) errors.push(`${path}: expected number`);
      break;
    case "boolean":
      if (typeof value !== "boolean") errors.push(`${path}: expected boolean`);
      break;
    case "array":
      if (!Array.isArray(value)) {
        errors.push(`${path}: expected array`);
      } else if (field.items) {
        value.forEach((item, i) => validateField(field.items as JsonSchemaField, item, `${path}[${i}]`, errors));
      }
      break;
    case "object":
      if (typeof value !== "object" || value === null || Array.isArray(value)) {
        errors.push(`${path}: expected object`);
        break;
      }
      validateObject(field, value as Record<string, unknown>, path, errors);
      break;
  }
}

function validateObject(
  field: JsonSchemaField,
  value: Record<string, unknown>,
  path: string,
  errors: string[]
): void {
  for (const key of field.required ?? []) {
    const v = value[key];
    if (v === undefined || v === null) errors.push(`${path}.${key}: missing required property`);
  }
  for (const [key, child] of Object.entries(field.properties ?? {})) {
    if (value[key] !== undefined) validateField(child, value[key], path ? `${path}.${key}` : key, errors);
  }
}

export function validateAgainstSchema(schema: JsonSchemaObject, input: unknown): ValidationResult {
  if (typeof input !== "object" || input === null || Array.isArray(input)) {
    return { ok: false, errors: ["input: expected object"] };
  }
  const errors: string[] = [];
  validateObject(schema, input as Record<string, unknown>, "", errors);
  return { ok: errors.length === 0, errors };
}

export function toolPromptDescription(tool: ToolDefinition): string {
  const params = Object.entries(tool.inputSchema.properties)
    .map(([k, v]) => `${k}:${v.type}${tool.inputSchema.required?.includes(k) ? "" : "?"}`)
    .join(", ");
  return `- ${tool.name} [${tool.category}, tier ${tool.riskTier}] ${tool.description} Args: ${params || "none"}`;
}

const TOOL_NAME_RE = /^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$/;

export class ToolRegistry {
  private tools = new Map<string, ToolDefinition>();

  register(tool: ToolDefinition): this {
    if (!TOOL_NAME_RE.test(tool.name)) throw new Error(`invalid tool name: ${tool.name}`);
    if (!tool.inputSchema || tool.inputSchema.type !== "object") {
      throw new Error(`tool ${tool.name} needs an object inputSchema`);
    }
    if (this.tools.has(tool.name)) throw new Error(`tool already registered: ${tool.name}`);
    this.tools.set(tool.name, tool);
    return this;
  }

  get(name: string): ToolDefinition | undefined {
    return this.tools.get(name);
  }

  has(name: string): boolean {
    return this.tools.has(name);
  }

  list(): ToolDefinition[] {
    return [...this.tools.values()].sort((a, b) => a.name.localeCompare(b.name));
  }

  listByCategory(category: ToolCategory): ToolDefinition[] {
    return this.list().filter((t) => t.category === category);
  }

  validateInput(name: string, input: unknown): ValidationResult {
    const tool = this.tools.get(name);
    if (!tool) return { ok: false, errors: [`unknown tool: ${name}`] };
    if (!tool.enabled) return { ok: false, errors: [`tool disabled: ${name}`] };
    return validateAgainstSchema(tool.inputSchema, input);
  }

  describeForLLM(): string {
    return this.list().map(toolPromptDescription).join("\n");
  }
}
