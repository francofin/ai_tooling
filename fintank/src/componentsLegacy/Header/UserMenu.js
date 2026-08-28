import React, { useEffect, useState, useContext } from "react"
import { Dropdown, NavLink, NavItem } from "react-bootstrap"
import ActiveLink from "@componentsLegacy/ActiveLink"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { faSignOutAlt } from "@fortawesome/free-solid-svg-icons"
import userMenu from "@data/user-menu.json"
import { getAuth, signOut  } from "firebase/auth";
import {fireBaseAuth} from '@utils/fireBaseUtility';
import Avatar from "@componentsLegacy/Avatar"
import { DjangoAuthContext } from '@context/authContext';
import { useRouter } from "next/router"

export default function UserMenu({ onLinkClick }) {

  const {logout, dispatch} = useContext(DjangoAuthContext);
  const router = useRouter();

  const logOutHandler = async() => {
    const auth = fireBaseAuth;
    await signOut(auth);

    dispatch({
      type:'LOGGED_IN_USER', 
      payload: null
    })

    logout();
    router.push('/login');
  }
  

  return (
    <Dropdown
      as={NavItem}
      className={userMenu.type === "avatar" ? "ms-lg-3" : ""}
    >
      <Dropdown.Toggle
        as={NavLink}
        style={userMenu.type === "avatar" && { padding: 0 }}
        className="dropdown-avatar"
      >
        {userMenu.type === "avatar" ? (
          <Avatar
            image={`/images/homepageImages/avatar.jpg`}
            alt={userMenu.title}
            className="me-2 avatar-border-white"
            size="sm"
            cover
          />
        ) : (
          userMenu.title
        )}
      </Dropdown.Toggle>
      <Dropdown.Menu align="end">
        {userMenu.dropdown &&
          userMenu.dropdown.map((dropdownItem, index) =>
            !dropdownItem.divider ? (
              <ActiveLink
                key={index}
                activeClassName="active"
                href={dropdownItem.link}
                passHref
              >
                <Dropdown.Item onClick={() => onLinkClick(userMenu.title)}>
                  {dropdownItem.title}
                </Dropdown.Item>
              </ActiveLink>
            ) : (
              <Dropdown.Divider key={index} />
            )
          )}
          <Dropdown.Item onClick={logOutHandler}>
            <FontAwesomeIcon
              icon={faSignOutAlt}
              className="me-2 text-muted"
            />
          Log Out
        </Dropdown.Item>
      </Dropdown.Menu>
    </Dropdown>
  )
}
