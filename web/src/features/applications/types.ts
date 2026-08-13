export interface ApplicationDefinitionSummary {
  business_code: string;
  version: string;
  name: string;
  region: string;
  official_service_name: string;
}

export interface ApplicationField {
  key: string;
  label: string;
  type: "text" | "phone" | "date" | "select";
  required?: boolean;
  editable?: boolean;
  sensitive?: boolean;
  options?: Array<{ label: string; value: boolean | string }>;
  value: unknown;
  source?: string;
  revision: number;
  sync_state: "pending" | "synced" | "rejected" | "conflict" | "readonly";
}

export interface ApplicationDetail {
  id: string;
  business_code: string;
  definition_version: string;
  status: string;
  current_step: string;
  definition: {
    name: string;
    region: string;
    official_service_name: string;
    steps: Array<{ code: string; name: string; state: string }>;
  };
  fields: ApplicationField[];
  materials: Array<{ key: string; label: string; required: boolean; status: string }>;
  browser?: { device_name: string; status: string; entry_url: string; adapter_id: string } | null;
  next_action?: { code: string; message: string };
}
