import { useState } from "react";

interface Props {
  name: string;
  logoUrl: string | null;
  size?: number;
}

function initials(name: string) {
  const words = name.trim().split(/\s+/).filter(Boolean);
  return (words.length > 1 ? words[0][0] + words[1][0] : name.slice(0, 2)).toUpperCase();
}

/** Stable hue per company, so its initials badge is always the same color. */
function hue(name: string) {
  let h = 0;
  for (const ch of name.toLowerCase()) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return h;
}

export default function CompanyLogo({ name, logoUrl, size = 20 }: Props) {
  const [failed, setFailed] = useState<string | null>(null);
  const style = { width: size, height: size, "--hue": hue(name), fontSize: size * 0.42 } as React.CSSProperties;

  if (logoUrl && failed !== logoUrl) {
    return (
      <span className="logo-img" style={style} aria-hidden>
        <img src={logoUrl} alt="" loading="lazy" draggable={false} onError={() => setFailed(logoUrl)} />
      </span>
    );
  }
  return (
    <span className="logo-initials" style={style} aria-hidden>
      {initials(name)}
    </span>
  );
}
