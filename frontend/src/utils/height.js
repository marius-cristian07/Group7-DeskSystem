export const MIN_HEIGHT_MM = 680;
export const MAX_HEIGHT_MM = 1320;

export function isValidHeight(mm) {
  return Number.isInteger(mm) && mm >= MIN_HEIGHT_MM && mm <= MAX_HEIGHT_MM;
}
