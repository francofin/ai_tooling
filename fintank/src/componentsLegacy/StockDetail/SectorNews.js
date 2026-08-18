import React from 'react';
import useSWR from 'swr';
import { Row, Col, Card, Spinner } from 'react-bootstrap';
import { fetchSectorNews, sectorNewsCategory } from '@utils/stockApi';

/**
 * The news feed is organised by topic, not by ticker, so this is the stock's
 * sector news rather than company news -- labelled as such so it isn't mistaken
 * for coverage of the symbol itself.
 */
const SectorNews = ({ sector }) => {
  const category = sectorNewsCategory(sector);
  // swr@1 spreads an array key across the fetcher's arguments (`fetcher(...key)`);
  // only swr@2 passes the array in as a single parameter. Destructuring the
  // first argument here therefore indexed into the *string* 'sector-news' and
  // requested /get_articles/e/, which 404s -- silently, because the error
  // branch below renders null. Take the second argument instead.
  const { data, error, isLoading } = useSWR(['sector-news', category], (_, c) => fetchSectorNews(c), {
    revalidateOnFocus: false,
  });

  if (error) return null;

  return (
    <div className="text-block">
      <h4 className="mb-1">Sector News</h4>
      <p className="text-muted text-sm mb-4">
        Headlines for {sector || 'the broader market'} — not specific to this company.
      </p>

      {isLoading && <Spinner animation="border" size="sm" />}

      <Row>
        {(data || []).slice(0, 6).map((article) => (
          <Col md="6" className="mb-4" key={article.link}>
            <Card className="h-100 border-0 shadow-sm">
              {article.thumbnail && (
                <Card.Img
                  variant="top"
                  src={article.thumbnail}
                  alt=""
                  style={{ objectFit: 'cover', height: '160px' }}
                />
              )}
              <Card.Body>
                <Card.Title className="h6">
                  <a href={article.link} target="_blank" rel="noreferrer" className="text-dark">
                    {article.title}
                  </a>
                </Card.Title>
                <Card.Text className="text-muted text-sm">{article.snippet}</Card.Text>
                <div className="text-muted text-sm">
                  {[article.source, article.date].filter(Boolean).join(' · ')}
                </div>
              </Card.Body>
            </Card>
          </Col>
        ))}
      </Row>
    </div>
  );
};

export default SectorNews;
