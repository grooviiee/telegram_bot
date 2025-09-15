"use client";

import { useState } from 'react';
import { Control } from './Control';
import { UserSwitcher } from './UserSwitcher';

export function InteractiveLayout() {
  const [userId, setUserId] = useState('');

  return (
    <>
      <UserSwitcher setUserId={setUserId} />
      <Control userId={userId} />
    </>
  );
}
