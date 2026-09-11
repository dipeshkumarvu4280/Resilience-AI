/**
 * Universal error parser to extract human-readable, safe error strings
 * from FastAPI backend responses (including validation errors, detail strings, arrays, and objects).
 */
export function formatApiError(err: any, fallback: string): string {
  if (!err) return fallback;
  
  const data = err.response?.data;
  if (data) {
    // If backend provided a direct message
    if (typeof data.message === 'string' && data.message.trim()) {
      return data.message;
    }

    // If detail is a simple string
    if (typeof data.detail === 'string' && data.detail.trim()) {
      return data.detail;
    }

    // If errors list is provided (e.g. from validation handler)
    if (Array.isArray(data.errors) && data.errors.length > 0) {
      return data.errors.join('; ');
    }

    // If detail is a list of Pydantic validation error objects
    if (Array.isArray(data.detail) && data.detail.length > 0) {
      return data.detail
        .map((d: any) => {
          if (typeof d === 'string') return d;
          const loc = Array.isArray(d.loc) ? d.loc.filter((l: any) => l !== 'body').join('.') : '';
          return loc ? `${loc}: ${d.msg || d.type}` : d.msg || d.type || JSON.stringify(d);
        })
        .join('; ');
    }
  }

  if (err.message && typeof err.message === 'string') {
    return err.message;
  }

  return fallback;
}
