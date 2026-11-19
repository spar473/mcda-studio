import { InfoDisclosure } from "./InfoDisclosure";
/** Engine diagnostics remain inspectable without obscuring the plain message. */
export function IssueText({ code, message, path }: { code: string; message: string; path?: string | null }) {
  return <><span>{message}</span> <InfoDisclosure label="Details for this message"><code className="issue-code">{code}</code>{path ? <span className="muted small"> {path}</span> : null}</InfoDisclosure></>;
}

/** Some service refusal messages carry their diagnostic prefix in the message itself. */
export function MessageText({ message }: { message: string }) {
  const prefix = /^([A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+):\s*/u.exec(message);
  if (!prefix) return <>{message}</>;
  const coded = /\b([A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+):\s*/gu;
  const codes = [...message.matchAll(coded)].map(match => match[1]);
  const readable = message.replace(coded, "");
  return <><span>{readable}</span> <InfoDisclosure label="Details for this message"><code>{codes.join(", ")}</code><br/>{message}</InfoDisclosure></>;
}
