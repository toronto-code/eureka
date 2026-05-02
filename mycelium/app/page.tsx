import Chat from './components/Chat'
import BulletinBoard from './components/BulletinBoard'
import StatusPanel from './components/StatusPanel'

export default function Home() {
  return (
    <main style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      <div style={{ padding: '16px 20px', borderBottom: '1px solid #eee', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h1 style={{ fontSize: '18px', fontWeight: 600 }}>Mycelium</h1>
          <p style={{ fontSize: '12px', color: '#888' }}>Company intelligence</p>
        </div>
      </div>
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        <div style={{ flex: 1, borderRight: '1px solid #eee', overflowY: 'auto' }}>
          <BulletinBoard />
        </div>
        <div style={{ flex: 2, display: 'flex', flexDirection: 'column' }}>
          <Chat />
        </div>
      </div>
      <StatusPanel />
    </main>
  )
}
