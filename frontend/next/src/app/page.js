
import { DashboardCard } from '@/components/DashboardCard';

// 메인 App 컴포넌트
export default async function App () {
  const resp = await fetch(`http://localhost:9999/topics`, {next: {revalidate: 0} });
  const topics = await resp.json()

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Dashboard</h1>
      <DashboardCard title="Welcome">
        <p>Hello World!</p>
      </DashboardCard>

      <div style={{ marginTop: '2rem' }}>
        <h2 className="text-xl font-bold">Topics</h2>
        {topics.map(topic => (
          <h1 key={topic.id}> {topic.id}: {topic.title}</h1>
        ))}
      </div>
    </div>
  );
};
