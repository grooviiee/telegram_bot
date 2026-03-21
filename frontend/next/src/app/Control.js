"use client"
import Link from 'next/link';
import { useParams } from 'next/navigation';

export function Control({ userId }) { // Receive userId as a prop
  const params = useParams();
  const isAdmin = userId === 'admin' && !!params.id;

  return (
    <ul>
      <h1> --- Control --- </h1>
      <li><Link href="/create">Go to Create</Link></li>
      {/* {id ? <> */}
      <li><Link href="/">Go to Homepage</Link></li>
      <li><Link href="/dividend">Go to Dividend check</Link></li>
      {/* Only show delete button if user is admin and on a topic page */}
      {isAdmin && <li><input type="button" value="delete"></input></li>}
      {/* </> : null} */}
    </ul>
  );
}