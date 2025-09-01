
import { DashboardCard } from '@/component/DashboardCard';

// 메인 App 컴포넌트
export default function App () {
  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Dashboard</h1>
      <DashboardCard title="Welcome">
        <p>Hello World!</p>
      </DashboardCard>
    </div>
  );
};
