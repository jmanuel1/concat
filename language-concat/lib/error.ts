export function isErrnoException(error: Error): error is NodeJS.ErrnoException {
  return Boolean((error as NodeJS.ErrnoException).code);
}
