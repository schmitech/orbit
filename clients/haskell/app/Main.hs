{-# LANGUAGE OverloadedStrings #-}
import qualified Data.Text as T
import Orbit.ApiClient (streamChat, StreamResponse(..))
import System.Environment (lookupEnv)

main :: IO ()
main = do
  url <- fmap (maybe "http://localhost:3000" T.pack) (lookupEnv "ORBIT_URL")
  putStrLn "Streaming example:"
  streamChat url Nothing Nothing "Hello from Haskell!" True $ \(StreamResponse t d) -> do
    putStr (T.unpack t)
    if d then putStrLn "" else pure ()

