
import { DashboardCard } from '@/components/DashboardCard';

// 메인 App 컴포넌트
export default async function App () {
  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Dashboard</h1>
      <DashboardCard title="Welcome">
        <p>Hello World!</p>
      </DashboardCard>

      <div style={{ marginTop: '2rem' }}>
      </div>
    </div>
  );
};
