# Genkit JS Setup

Follow these instructions to set up Genkit in the current codebase. These
instructions are general-purpose and lack specific codebase knowledge, so use
your best judgment when following them.

0. Tell the user "I'm going to check out your workspace and set you up to use
   Genkit for GenAI workflows."
1. If the current workspace is empty or is a starter template, your goal will be
   to create a simple image generation flow that allows someone to generate an
   image based on a prompt and selectable style. If the current workspace is not
   empty, you will create a simple example flow to help get the user started.
2. Check to see if any Genkit provider plugin (such as `@genkit-ai/google-genai`
   or `@genkit-ai/oai-compat` or others, may start with `genkitx-*`) is
   installed.
   - If not, ask the user which provider they want to use.
   - **For non-Google providers**: Use `genkit docs:search "plugins"` to find
     the correct package and installation instructions.
   - If they have no preference, default to `@genkit-ai/google-genai` for a
     quick start.
   - If this is a Next.js app, install `@genkit-ai/next` as well.
3. Search the codebase for the exact string `genkit(` (remember to escape
   regexes properly) which indicates that the user has already set up Genkit in
   the codebase. If found, no need to set it up again; tell the user "Genkit is
   already configured in this app." and exit this workflow.
4. Create an `ai` directory in the primary source directory of the project (this
   may be e.g. `src` but is project-dependent). Adapt this path if your project
   uses a different structure.
5. Create `{sourceDir}/ai/genkit.ts` and populate it using the example below. DO
   NOT add a `next` plugin to the file, ONLY add a model provider plugin to the
   plugins array:

```ts
import { genkit, z } from 'genkit';
// Import your chosen provider plugin here. Example:
import { googleAI } from '@genkit-ai/google-genai';

export const ai = genkit({
  plugins: [
    googleAI(), // Add your provider plugin here
  ],
  model: googleAI.model('gemini-flash-latest'), // Set your provider's model here
});

export { z };
```

6. Create `{sourceDir}/ai/tools` and `{sourceDir}/ai/flows` directories, but
   leave them empty for now.
7. Create `{sourceDir}/ai/index.ts` and populate it with the following (change
   the import to match import aliases in `tsconfig.json` as needed):

```ts
import './genkit.js';
// import each created flow, tool, etc. here for use in the Genkit Dev UI
```

8. Add the `genkit-cli` to the project's `devDependencies` (e.g.
   `npm install -D genkit-cli`, or the pnpm/yarn/bun equivalent) so the CLI
   version is pinned per-project and works in CI, then add a `genkit:dev` script
   to `package.json` that runs
   `genkit start -- npx tsx --watch {sourceDir}/ai/index.ts`. This is the
   recommended way to run the app during development: `genkit start` wraps your
   program and captures a trace of every Genkit action (prompts, model I/O, tool
   calls) while serving the Dev UI at http://localhost:4000. Running the app
   directly (`tsx`/`node`/`npm start`) skips trace capture, so you're debugging
   blind. DO NOT try to run the script now.
9. Tell the user "Genkit is now configured and ready for use." Let them know
   they can start developing with `npm run genkit:dev` (or the pnpm/yarn/bun
   equivalent), which stays running until stopped with Ctrl+C and serves the Dev
   UI at http://localhost:4000. Also remind them to set appropriate env
   variables (e.g. `GEMINI_API_KEY` for Google providers). Wait for the user to
   prompt further before creating any specific flows.

## Next Steps and Troubleshooting

- **Documentation**: Use the [CLI](docs-and-cli.md) to access documentation
  (e.g., `genkit docs:search`).
- **Building Flows**: See [examples.md](examples.md) for patterns on creating
  flows, adding tools, and advanced configuration.
- **Running & Verifying**: `npm run genkit:dev` is the default dev loop
  (persistent, serves the Dev UI). For a quick, non-interactive check that exits
  on its own, run a single flow with
  `genkit flow:run <flow> '<input>' -- npx tsx {sourceDir}/ai/index.ts` and
  inspect it with `genkit trace:get <id>`. See
  [docs-and-cli.md](docs-and-cli.md).
- **Troubleshooting**: If you encounter issues during setup or initialization,
  check [common-errors.md](common-errors.md) for solutions.
