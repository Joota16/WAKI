// Reutiliza los tokens del formulario sin ejecutar Tailwind en el navegador.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const context = { tailwind: {} };
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../app/static/js/config/tailwind-citizen.js'), 'utf8'), context);
const config = context.tailwind.config;
config.content = ['./app/templates/**/*.html', './app/static/js/**/*.js'];
config.plugins = [require('@tailwindcss/forms'), require('@tailwindcss/container-queries')];
for (const fonts of Object.values(config.theme.extend.fontFamily)) fonts.push('system-ui', 'sans-serif');
module.exports = config;
