import React, {useState, useEffect, useContext} from 'react';
import swal from 'sweetalert';
import { AccountContext } from '@context/accountContext';

export const useUserAccounts = () => {

    const {loading, accounts, addAccount} = useContext(AccountContext);

    return {loading, accounts, addAccount}
}