import React from 'react';
import { MemoryRouter } from 'react-router-dom';
import { render, waitFor } from '@testing-library/react';
import App from './App';

describe('Components/App', () => {
  test('renders the diagnostics search page', async () => {
    const { queryByText } = render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <App />
      </MemoryRouter>
    );

    // Application is lazy loaded, so we need to wait for the component and routes to be rendered
    await waitFor(() => expect(queryByText(/XConnect 用户慢连接诊断/i)).toBeInTheDocument(), { timeout: 2000 });
  });
});
