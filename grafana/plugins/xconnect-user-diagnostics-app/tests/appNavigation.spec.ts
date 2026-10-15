import { test, expect } from './fixtures';

test.describe('navigating app', () => {
  test('diagnostics page renders without placing identity in its URL', async ({ gotoPage, page }) => {
    await gotoPage('/');
    await expect(page.getByText('XConnect 用户慢连接诊断')).toBeVisible();
    await expect(page).toHaveURL(/\/a\/aiworkspace-xconnectuserdiagnostics-app\/?$/);
  });
});
