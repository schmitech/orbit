{-# LANGUAGE OverloadedStrings #-}
module Orbit.ApiClient
  ( StreamResponse(..)
  , streamChat
  ) where

import           Control.Monad.IO.Class   (liftIO)
import           Data.Aeson               (Value (..), decode, (.:), withObject)
import           Data.Aeson.Types         (parseMaybe)
import qualified Data.ByteString          as BS
import qualified Data.ByteString.Char8    as C8
import qualified Data.ByteString.Lazy     as LBS
import           Data.Conduit             (ConduitT, (.|), runConduitRes, yield)
import qualified Data.Conduit.Binary      as CB
import qualified Data.Conduit.List        as CL
import qualified Data.Text                as T
import qualified Data.Text.Encoding       as TE
import           Network.HTTP.Client      (RequestBody (..))
import           Network.HTTP.Simple

data StreamResponse = StreamResponse { text :: T.Text, done :: Bool } deriving (Show, Eq)

endpoint :: T.Text -> T.Text
endpoint url = if "/v1/chat" `T.isSuffixOf` url then url else T.dropWhileEnd (== '/') url <> "/v1/chat"

-- | Stream chat with a callback per chunk
streamChat :: T.Text -> Maybe T.Text -> Maybe T.Text -> T.Text -> Bool -> (StreamResponse -> IO ()) -> IO ()
streamChat apiUrl mApiKey mSessionId message stream onChunk = do
  let jsonBody = LBS.fromStrict $ TE.encodeUtf8 $ T.concat
        [ "{\"messages\":[{\"role\":\"user\",\"content\":\""
        , escape message
        , "\"}],\"stream\":"
        , if stream then "true" else "false"
        , "}"
        ]
  initReq <- parseRequest (T.unpack ("POST " <> endpoint apiUrl))
  let req = setRequestBodyLBS jsonBody
          $ setRequestHeader "Content-Type" ["application/json"]
          $ setRequestHeader "Accept" [if stream then "text/event-stream" else "application/json"]
          $ maybe id (\k -> setRequestHeader "X-API-Key" [TE.encodeUtf8 k]) mApiKey
          $ maybe id (\s -> setRequestHeader "X-Session-ID" [TE.encodeUtf8 s]) mSessionId
          $ initReq

  if not stream
    then do
      rsp <- httpLBS req
      let body = getResponseBody rsp
      case decode body :: Maybe Value of
        Just v ->
          case parseMaybe (withObject "res" (\o -> o .: "response")) v of
            Just t  -> onChunk (StreamResponse (T.pack t) True)
            Nothing -> onChunk (StreamResponse (TE.decodeUtf8 $ LBS.toStrict body) True)
        Nothing -> onChunk (StreamResponse (TE.decodeUtf8 $ LBS.toStrict body) True)
    else runConduitRes $
      httpSource req getResponseBody
      .| CB.lines
      .| CL.mapM_ (\bs -> liftIO $ handleLine bs)
 where
  handleLine :: BS.ByteString -> IO ()
  handleLine raw = do
    let line = C8.unpack (C8.strip raw)
    if null line then pure ()
    else if "data: " `isPrefix` line
      then do
        let jsonTxt = drop 6 line
        if null (trim jsonTxt) || trim jsonTxt == "[DONE]"
          then onChunk (StreamResponse "" True)
          else case decode (LBS.fromStrict $ C8.pack jsonTxt) :: Maybe Value of
                 Just v -> do
                   let mt = parseMaybe (withObject "res" (\o -> o .: "response")) v
                       md = parseMaybe (withObject "res" (\o -> o .: "done")) v :: Maybe Bool
                   case mt of
                     Just t  -> onChunk (StreamResponse (T.pack t) (maybe False id md))
                     Nothing -> onChunk (StreamResponse (T.pack jsonTxt) False)
                 Nothing -> onChunk (StreamResponse (T.pack jsonTxt) False)
      else onChunk (StreamResponse (TE.decodeUtf8 $ C8.pack line) False)

  isPrefix p s = take (length p) s == p
  trim = reverse . dropWhile (== ' ') . reverse . dropWhile (== ' ')
  escape = T.concatMap (\c -> case c of
    '\\' -> "\\\\"; '"' -> "\\\""; '\n' -> "\\n"; '\r' -> "\\r"; '\t' -> "\\t"; x -> T.singleton x)

