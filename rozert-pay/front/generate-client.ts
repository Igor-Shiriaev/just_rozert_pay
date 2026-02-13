const { generate } = require('openapi-typescript-codegen');
const chokidar = require('chokidar');
const fs = require('fs').promises;
const fsSync = require('fs');
const path = require('path');

const INPUT_FILE = 'swagger.yml';
const OUTPUT_DIR = './src/api';
const INPUT_PATH = path.resolve(INPUT_FILE);
const OUTPUT_PATH = path.resolve(OUTPUT_DIR);

const GENERATION_OPTIONS = {
  input: INPUT_PATH,
  output: OUTPUT_PATH,
  httpClient: 'fetch',
  useOptions: true,
  useUnionTypes: true,
};

const removeDirectory = async (dir: any) => {
  const entries = await fs.readdir(dir, { withFileTypes: true });
  await Promise.all(entries.map(async (entry: any) => {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      await removeDirectory(fullPath);
    } else {
      await fs.unlink(fullPath);
    }
  }));
  await fs.rmdir(dir);
};

const generateClient = async () => {
  console.log('Generating client...');
  try {
    if (await fs.stat(OUTPUT_PATH).catch(() => false)) {
      await removeDirectory(OUTPUT_PATH);
    }
    await generate(GENERATION_OPTIONS);
    console.log('Client generated successfully');
  } catch (error) {
    console.error('Error generating client:', error);
  }
};

const watcher = chokidar.watch(INPUT_PATH, {
  persistent: true
});

watcher
  .on('add', generateClient)
  .on('change', generateClient);

console.log(`Watching for changes in ${INPUT_PATH}...`);

if (fsSync.existsSync(INPUT_PATH)) {
  generateClient();
}
