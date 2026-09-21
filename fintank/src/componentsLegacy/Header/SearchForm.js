import React, { useState } from "react"
import { Form, Button, ListGroup, OverlayTrigger  } from "react-bootstrap"
import { useStockNames } from "@hooks/useStockNames"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { faSearch, faTimes } from "@fortawesome/free-solid-svg-icons"
import { useRouter } from "next/router"
import { tickerHref } from "@utils/stockApi"
export default function SearchForm({ id, className, childClassname }) {
  const [searchFocus, setSearchFocus] = useState(false)
  const [activeSuggestion, setActiveSuggestion] = useState(0)
  const [filteredSuggestions, setFilteredSuggestions] = useState([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [ticker, setTicker] = useState('')
  const [searchTicker, setSearchTicker] = useState('')
  const onFocus = () => setSearchFocus(!searchFocus)
  const router = useRouter();

  const {data:stockNames} = useStockNames();
  const allStocks = stockNames?.stocks

  // Navigate to whatever is actually in the box. `searchTicker` is only set by
  // picking a suggestion, so submitting a typed ticker used to push
  // /stock-data/ with an empty segment.
  const goToTicker = (symbol) => {
    const target = String(symbol ?? '').trim()
    if (!target) return
    setShowSuggestions(false)
    setFilteredSuggestions([])
    setActiveSuggestion(0)
    // Send funds to /etf-data/ directly -- /stock-data/ has no ETF profile and
    // would bounce through a redirect. all-stock-names carries is_etf, so the
    // lookup is local; a ticker that matches nothing still goes to /stock-data/,
    // which resolves or 404s on its own.
    const match = allStocks?.find(
      (s) => s['symbol'].toLowerCase() === target.toLowerCase()
    )
    router.push(tickerHref(target, match?.is_etf))
  }

  const returnQuery = (e) => {
    e.preventDefault();

    goToTicker(searchTicker || ticker)
  }


  const onSearchChange = (e) => {
    const userInput = e.target.value;

    // Filter our suggestions that don't contain the user's input
    const suggestionFilter = allStocks?.filter(
      suggestion =>
        (suggestion['symbol'].toLowerCase().indexOf(userInput.toLowerCase()) > -1) || (suggestion['name'].toLowerCase().indexOf(userInput.toLowerCase()) > -1)
    );


    // Reset the highlight on every keystroke: the list is rebuilt here, so a
    // carried-over index can point past the end of the new, shorter list and
    // make Enter select the wrong row.
    setActiveSuggestion(0)
    setFilteredSuggestions(suggestionFilter)
    setShowSuggestions(true)
    setTicker(userInput)
  };


  // Bound to the input, not to the suggestion list -- the list is a div that
  // never takes focus, so none of these keys reached this handler before.
  const onKeySuggestDown = (e) => {
    const suggestions = filteredSuggestions || []

    // User pressed the enter key
    if (e.keyCode === 13) {
      // The form's onSubmit also fires on Enter; let the highlighted
      // suggestion win while the list is open.
      if (showSuggestions && suggestions[activeSuggestion]) {
        e.preventDefault()
        onSuggestionClick(suggestions[activeSuggestion]['symbol'])
      }
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
      if (activeSuggestion >= suggestions.length - 1) {
        return;
      }

      setActiveSuggestion(activeSuggestion + 1);
    }
  };

  // Picking a suggestion has to navigate. It used to only fill the input and
  // close the list, so a click looked like it did nothing at all.
  const onSuggestionClick = (item) => {

    setSearchTicker(item)
    setTicker(item)
    goToTicker(item)

  };

  const renderSuggestedList = () => {
    return(
    <ListGroup variant="flush" className="d-inline-block" style={{position:'absolute'}}>
      {filteredSuggestions?.map((suggestion, i) => {
        return(
          <ListGroup.Item
            key={i}
            as="li"
            action
            active={i === activeSuggestion}
            // onMouseDown fires before the input's onBlur, so the selection
            // cannot be torn down before the click lands.
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => onSuggestionClick(suggestion['symbol'])}
          >
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
          onKeyDown={(e) => onKeySuggestDown(e)}
          onBlur={() => setTimeout(() => onFocus(), 333)}
          
        />
        
        <Button variant="reset" size="sm" type="reset" onClick={resetTicker}>
          <FontAwesomeIcon icon={faTimes} />
        </Button>
      </div>
    </Form>
    {(showSuggestions && filteredSuggestions?.length < 40) ?
      <div>
        {renderSuggestedList()}
      </div>:
      ""
      }
    
    </>
  )
}
