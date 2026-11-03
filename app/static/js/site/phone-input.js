export function initPhoneInput(input) {
  if (!input) return () => {};
  function normalize() {
    let value = input.value.replace(/[\s()\-]/g, '');
    if (value.startsWith('+51')) value = value.slice(3);
    else if (value.startsWith('51') && value.length === 11) value = value.slice(2);
    if (/^9[0-9]{8}$/.test(value)) input.value = value;
    input.setCustomValidity(input.value && !/^9[0-9]{8}$/.test(input.value)
      ? 'Ingresa un celular de 9 dígitos que empiece con 9.' : '');
  }
  input.addEventListener('input', normalize);
  input.addEventListener('blur', normalize);
  normalize();
  return normalize;
}
