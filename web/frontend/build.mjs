// ztd-charts + React → 단일 IIFE 번들(static/js/vendor/ztd-charts.min.js)과 Pretendard 글꼴 복사.
// 실행: cd web/frontend && npm ci && npm run build   (결과물은 저장소에 커밋 → Maven 빌드에 Node 불필요)
import { build } from "esbuild";
import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const statics = join(here, "../src/main/resources/static");
const vendor = join(statics, "js/vendor");
const fonts = join(statics, "fonts");
mkdirSync(vendor, { recursive: true });
mkdirSync(fonts, { recursive: true });

await build({
  entryPoints: [join(here, "charts.jsx")],
  outfile: join(vendor, "ztd-charts.min.js"),
  bundle: true,
  format: "iife",
  platform: "browser",
  target: "es2020",
  minify: true,
  jsx: "automatic",
  legalComments: "none",
  define: { "process.env.NODE_ENV": '"production"' },
  logLevel: "info",
});

const pkg = (p) => JSON.parse(readFileSync(join(here, "node_modules", p, "package.json"), "utf8"));
writeFileSync(join(vendor, "ztd-charts-LICENSE.md"),
  `ztd-charts ${pkg("ztd-charts").version} (MIT) — https://github.com/Junhan2/ztd-charts\n` +
  `React / React DOM ${pkg("react").version} (MIT) — https://react.dev\n\n` +
  readFileSync(join(here, "node_modules/react/LICENSE"), "utf8"));

copyFileSync(join(here, "node_modules/pretendard/dist/web/variable/woff2/PretendardVariable.woff2"),
  join(fonts, "PretendardVariable.woff2"));
// npm 패키지에는 LICENSE 파일이 없어 출처·라이선스만 적어 둡니다(SIL Open Font License 1.1)
writeFileSync(join(fonts, "Pretendard-LICENSE.txt"),
  `Pretendard ${pkg("pretendard").version} — Copyright (c) 2021, Kil Hyung-jin (https://github.com/orioncactus/pretendard)\n` +
  "Licensed under the SIL Open Font License, Version 1.1 — https://openfontlicense.org\n");
console.log("fonts: PretendardVariable.woff2 (OFL-1.1)");
