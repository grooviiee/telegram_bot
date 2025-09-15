
export const DashboardCard = ({ title, children }) => {
  return (
    <div style={{ border: '1px solid #ccc', padding: '16px', borderRadius: '8px', margin: '16px 0' }}>
      {title && <h2 style={{ marginTop: 0 }}>{title}</h2>}
      <div>{children}</div>
    </div>
  );
};
