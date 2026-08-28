import React, {useState} from "react"
import Link from "next/link"
import Stars from "@componentsLegacy/Stars"
import {
  Container,
  Row,
  Button,
  Table,
  Breadcrumb,
  Badge,
} from "react-bootstrap"





const ValuationsTable = (props) => {

  const [analysisLink, setAnalysisLink] = useState("/stock-data/[ticker]");
  const [linkAs, setLinkAs] = useState(`/stock-data/`)


  return(
    <section className="py-2">
    <Container>
      <Row>
        <Table striped responsive hover className="text-gray-700 text-sm">
          <tbody>
          
              <tr>
                <th className="py-4 align-middle">Stock</th> 
                <th className="py-4 align-middle">Name</th> 
                <th className="py-4 align-middle">Price/Earnings</th>  
                <th className="py-4 align-middle">EPS</th>  
                <th className="py-4 align-middle">% Change</th>  
                <th className="py-4 align-middle">Price</th> 
                <th className="py-4 align-middle">Market Cap</th> 
              </tr>
              
              {props.valuations &&
                props.valuations?.map((item) => (
                  <tr key={item.symbol} className="py-4 text-center align-middle">
                    {/* {Object.values(item).map((val) => (
                          <td>{val}</td>
                      ))} */}
                      <td><Link href={analysisLink} as={`${linkAs}${item.symbol}`} passHref >{item.symbol}</Link></td>
                      <td>{item.name}</td>
                      <td>{item.pe}</td>
                      <td>{item.eps}</td>
                      <td>{item.changesPercentage}</td>
                      <td>{item.price}</td>
                      <td>{item.marketCap}</td>
                    
                  </tr>
                ))}
              
            
            
          </tbody>
        </Table>
      </Row>
    </Container>
  </section>
  )}
  
  export default ValuationsTable