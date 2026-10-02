/**
 * errorMessage has to cope with three different shapes FastAPI returns and one
 * it does not return at all - a network failure, where showing the fallback
 * ("Something went wrong") hides the only thing worth saying, which is that the
 * backend is not running.
 */

import { AxiosError, AxiosHeaders } from 'axios';
import { describe, expect, it } from 'vitest';
import { errorMessage } from './api';

function axiosError(data: unknown, status = 400): AxiosError {
  const error = new AxiosError('Request failed');

  error.response = {
    data,
    status,
    statusText: '',
    headers: {},
    config: { headers: new AxiosHeaders() }
  };

  return error;
}

describe('errorMessage', () => {
  it('uses a string detail, which is what HTTPException raises', () => {
    expect(errorMessage(axiosError({ detail: 'That user is already a member.' }))).toBe(
      'That user is already a member.'
    );
  });

  it('uses the first message from a Pydantic validation array', () => {
    const detail = [
      { loc: ['body', 'email'], msg: 'value is not a valid email address', type: 'value_error' },
      { loc: ['body', 'password'], msg: 'too short', type: 'value_error' }
    ];

    expect(errorMessage(axiosError({ detail }))).toBe('value is not a valid email address');
  });

  it('says the backend is unreachable when there is no response at all', () => {
    const error = new AxiosError('Network Error');

    expect(errorMessage(error)).toBe('Cannot reach the server. Is the backend running?');
  });

  it('falls back when the body carries no detail', () => {
    expect(errorMessage(axiosError({}), 'Could not load usage')).toBe('Could not load usage');
  });

  it('falls back for an empty validation array rather than reading index zero', () => {
    expect(errorMessage(axiosError({ detail: [] }), 'Could not save')).toBe('Could not save');
  });

  it('falls back for something that is not an axios error', () => {
    expect(errorMessage(new TypeError('x is not a function'), 'Could not load')).toBe(
      'Could not load'
    );
  });
});
