import React, { useState } from "react"
import { Form, Button, ListGroup, OverlayTrigger  } from "react-bootstrap"
import { useStockNames } from "@hooks/useStockNames"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { faSearch, faTimes } from "@fortawesome/free-solid-svg-icons"
import { useRouter } from "next/router"
export default function SearchForm({ id, className, childClassname }) {
  const [searchFocus, setSearchFocus] = useState(false)
  const [activeSuggestion, setActiveSuggestion] = useState(0)
  const [filteredSuggestions, setFilteredSuggestions] = useState([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [ticker, setTicker] = useState('')
  const [searchTicker, setSearchTicker] = useState('')
  const onFocus = () => setSearchFocus(!searchFocus)
  const router = useRouter();

  
  const returnQuery = (e) => {
    e.preventDefault();

    router.push(`/stock-data/${searchTicker}`)
  }


  const {data:stockNames} = useStockNames();
  const allStocks = stockNames?.stocks


  const onSearchChange = (e) => {
    const userInput = e.target.value;

    // Filter our suggestions that don't contain the user's input
    const suggestionFilter = allStocks?.filter(
      suggestion =>
        (suggestion['symbol'].toLowerCase().indexOf(userInput.toLowerCase()) > -1) || (suggestion['name'].toLowerCase().indexOf(userInput.toLowerCase()) > -1)
    );


    // setActiveSuggestion(0)
    setFilteredSuggestions(suggestionFilter)
    setShowSuggestions(true)
    setTicker(userInput)
  };


  const onKeySuggestDown = (e) => {
    // const { activeSuggestion, filteredSuggestions } = this.state;

    // User pressed the enter key
    if (e.keyCode === 13) {
      setActiveSuggestion(0)
      setShowSuggestions(false)
      setTicker(filteredSuggestions[activeSuggestion])
    }
    // User pressed the up arrow
    else if (e.keyCode === 38) {
      if (activeSuggestion === 0) {
        return;
      }

      setActiveSuggestion(activeSuggestion - 1);
    }
    // User pressed the down arrow
    else if (e.keyCode === 40) {
      if (activeSuggestion - 1 === filteredSuggestions.length) {
        return;
      }

      setActiveSuggestion(activeSuggestion + 1);
    }
  };

  const onSuggestionClick = (item) => {

    setActiveSuggestion(0)
    setShowSuggestions(false)
    setFilteredSuggestions([])
    setSearchTicker(item)
    setTicker(item)

  };

  const renderSuggestedList = () => {
    return(
    <ListGroup variant="flush" className="d-inline-block" style={{position:'absolute'}}>
      {filteredSuggestions?.map((suggestion, i) => {
        return(
          <ListGroup.Item key={i} as="li" onClick={() => onSuggestionClick(suggestion['symbol'])}>
                {suggestion['symbol']} - {suggestion['name']} - {suggestion['exchange']}
            </ListGroup.Item>
        )
      })}
    </ListGroup>
    )
  }


  const resetTicker = () => {
    // e.preventDefault()
    setTicker('')
    setFilteredSuggestions([])
    setActiveSuggestion(0)
    setShowSuggestions(false)
  }


  return (
    <>
    <Form id={id} className={className} onSubmit={returnQuery}>
      <div
        className={`input-label-absolute input-label-absolute-left input-reset ${
          childClassname ? childClassname : ""
        } ${searchFocus ? "focus" : ""}`}
      >
        <label htmlFor={id + "_search"} className="label-absolute">
          <FontAwesomeIcon icon={faSearch} />
          <span className="sr-only">What are you looking for?</span>
        </label>
        <Form.Control
          id={id + "_search"}
          placeholder="Search Ticker"
          aria-label="Search"
          size="sm"
          value={ticker}
          className="border-0 shadow-0 bg-gray-200"
          autoComplete="off"
          onFocus={onFocus}
          onChange ={(e) => onSearchChange(e)}
          onBlur={() => setTimeout(() => onFocus(), 333)}
          
        />
        
        <Button variant="reset" size="sm" type="reset" onClick={resetTicker}>
          <FontAwesomeIcon icon={faTimes} />
        </Button>
      </div>
    </Form>
    {(showSuggestions && filteredSuggestions?.length < 40) ?
      <div onKeyDown = {(e) => onKeySuggestDown(e)}s>
        {renderSuggestedList()}
      </div>:
      ""
      }
    
    </>
  )
}
