export type LoginRequest = {
  employee_id: string;
  password: string;
};

export type LoginRole = {
  id: number;
  name: string;
  type: string;
};

export type LoginUser = {
  id: number;
  employee_id: string;
  name: string;
};

export type LoginResponse = {
  access_token: string;
  token_type: "bearer";
  user: LoginUser;
  roles: LoginRole[];
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export async function login(payload: LoginRequest): Promise<LoginResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail ?? "Login failed. Please try again.");
  }

  return response.json() as Promise<LoginResponse>;
}
