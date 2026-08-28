import React, {useReducer,useState, createContext, useEffect} from 'react';
import swal from 'sweetalert';

//reducer functions update state
const initialState = {
    user: null,
};


const AccountContext = createContext();

const AccountContextProvider = ({children}) => {
    const [loading, setLoading] = useState(true);
    const [accounts, setAccounts] = useState([]);


    const addAccount = (account) => {
        // setAccounts((previousAccounts) => [...previousAccounts, account]);
        setAccounts((prevAccounts) => {
            const updatedAccounts = [...prevAccounts, account];
            localStorage.setItem("XRP_accounts", JSON.stringify(updatedAccounts));
            return updatedAccounts;
        })
    }

    return(
        <AccountContext.Provider value={{loading, accounts, addAccount}}>
            {children}
        </AccountContext.Provider>
    )
}

export {AccountContext, AccountContextProvider}