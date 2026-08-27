"use client";

import { FormEvent, Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { authClient } from "@/lib/auth-client";
import {
  Button,
  ErrorNote,
  Field,
  Input,
  Surface,
  TechnicalLabel,
} from "@/components/ui/primitives";
import { GibbsLockup } from "@/components/ui/Logo";

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));

  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    const result =
      mode === "signin"
        ? await authClient.signIn.email({ email, password })
        : await authClient.signUp.email({
            email,
            password,
            name: name.trim() || email.split("@")[0],
          });
    setBusy(false);
    if (result.error) {
      setError(result.error.message ?? "Authentication failed");
      return;
    }
    router.replace(next);
    router.refresh();
  }

  return (
    <div className="relative isolate flex min-h-screen items-center justify-center px-4">
      <div
        aria-hidden
        className="bg-grid pointer-events-none absolute inset-x-0 top-0 -z-10 h-[520px]"
      />
      <Surface className="w-full max-w-sm p-6">
        <div className="mb-6 flex flex-col gap-1">
          <GibbsLockup className="mb-1" />
          <TechnicalLabel>{mode === "signin" ? "sign in" : "create account"}</TechnicalLabel>
        </div>

        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          {mode === "signup" && (
            <Field label="Name">
              <Input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" />
            </Field>
          )}
          <Field label="Email">
            <Input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
            />
          </Field>
          <Field label="Password" hint={mode === "signup" ? "at least 8 characters" : undefined}>
            <Input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "signin" ? "current-password" : "new-password"}
            />
          </Field>

          {error && <ErrorNote>{error}</ErrorNote>}

          <Button type="submit" variant="primary" loading={busy} className="mt-1 w-full">
            {mode === "signin" ? "Sign in" : "Sign up"}
          </Button>
        </form>

        <button
          type="button"
          onClick={() => {
            setMode(mode === "signin" ? "signup" : "signin");
            setError(null);
          }}
          className="mt-4 text-[12px] text-text-secondary underline decoration-dotted underline-offset-4 hover:text-text"
        >
          {mode === "signin" ? "No account? Sign up" : "Have an account? Sign in"}
        </button>
      </Surface>
    </div>
  );
}

/** Only allow same-origin relative redirects. */
function safeNext(value: string | null): string {
  if (!value || !value.startsWith("/") || value.startsWith("//")) return "/campaigns";
  return value;
}
